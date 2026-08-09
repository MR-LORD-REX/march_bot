"""Lore chatbot: one stateless Gemini call per question, routed through the
key/model pool.

The previous version held a persistent `client.aio.chats` session on the
ChatBot instance, so every user in the bot shared one thread and one key.
Now history comes from Redis per telegram id and each API call reserves a
(key, model) bucket from the quota manager -- which is also what makes the
two-model / N-key fan-out possible, since a retry can land on a different
key than the first attempt.
"""

from dataclasses import dataclass
import logging

from pydantic import BaseModel

from bot.config.config import QDRANT_API_KEY, QDRANT_URL, EMBEDDING_URL
from bot.services.lorebot.config import (
    REWRITE_PROMPT,
    SYSTEM_PROMPT,
    HANDOFF_REWRITE_PROMPT,
)
from bot.services.lorebot.utils import Retriever, build_context, vdb_search, Passage

logger = logging.getLogger(__name__)

for _var, _name in (
    (QDRANT_API_KEY, "QDRANT_API_KEY"),
    (QDRANT_URL, "QDRANT_URL"),
    (EMBEDDING_URL, "EMBEDDING_URL"),
):
    if not _var:
        raise ValueError(f"Missing required environment variable: {_name}")


@dataclass
class Turn:
    q: str
    a: str


class ChatResponse(BaseModel):
    question: str
    answer: str
    error: str | None = None
    search_query: str | None = None
    # ok | rpm | rpd | empty | error -- the handler branches on this to decide
    # between answering, asking the user to retry, and disabling /ask
    status: str = "ok"


@dataclass
class _Gen:
    status: str
    text: str = ""
    error: str = ""


def _is_rate_limited(e: Exception) -> bool:
    msg = str(e).lower()
    return (
        "429" in msg
        or "resource_exhausted" in msg
        or "resource exhausted" in msg
        or "rate limit" in msg
        or "quota" in msg
    )


def _is_daily_limit(e: Exception) -> bool:
    """Distinguish 'slow down' from 'come back tomorrow'. Google spells the
    daily bucket out in the violation string; when it doesn't, treating it as
    per-minute is the safe guess -- a wrong daily verdict would take /ask
    offline for the rest of the day."""
    msg = str(e).lower()
    return "perday" in msg or "per day" in msg or "requests per day" in msg


def _afc_extra_calls(resp) -> int:
    """Extra API calls the SDK made on our behalf.

    Automatic function calling loops back to the model once per tool round,
    and Google bills each of those. We reserve one slot up front, so the rest
    have to be charged after the fact or the counters drift low and we walk
    into real 429s.
    """
    history = getattr(resp, "automatic_function_calling_history", None) or []
    extra = 0
    for content in history:
        if getattr(content, "role", None) != "model":
            continue
        for part in (getattr(content, "parts", None) or []):
            if getattr(part, "function_call", None):
                extra += 1
                break
    return extra


def _text_of(resp) -> str:
    try:
        if resp.text:
            return resp.text.strip()
    except Exception:
        pass
    try:
        for part in resp.candidates[0].content.parts:
            if getattr(part, "text", None):
                return part.text.strip()
    except Exception:
        pass
    return ""


class ChatBot:
    def __init__(
        self,
        quota=None,
        retriever: Retriever | None = None,
        top_k: int = 15,
        prefetch: int = 60,
        temperature: float = 0.2,
    ):
        self._quota = quota
        self._retriever = retriever
        self.top_k = top_k
        self.prefetch = prefetch
        self.temperature = temperature
        self._clients: dict[str, object] = {}

    # ------------------------------------------------------------------
    # lazily-built collaborators (import order + startup ordering)
    # ------------------------------------------------------------------

    @property
    def quota(self):
        if self._quota is None:
            from bot.services.lorebot.quota import QuotaManager

            # A ChatBot built without a pool gets its own; the shared instance
            # in runtime.py is constructed with quota= explicitly.
            self._quota = QuotaManager()
        return self._quota

    @property
    def retriever(self) -> Retriever:
        if self._retriever is None:
            self._retriever = Retriever()
        return self._retriever

    def _client(self, api_name: str, api_key: str):
        """One genai.Client per key, reused across requests -- each carries an
        HTTP pool, and building one per /ask leaks connections."""
        client = self._clients.get(api_name)
        if client is None:
            from google import genai

            client = genai.Client(api_key=api_key)
            self._clients[api_name] = client
        return client

    def drop_clients(self) -> None:
        """Called after a key is edited or removed so a stale key is not held."""
        self._clients.clear()

    # ------------------------------------------------------------------
    # model access
    # ------------------------------------------------------------------

    async def _generate(self, contents, config, wait: int, attempts: int = 2) -> _Gen:
        """Run one generation, failing over to another bucket on a 429.

        `wait` only applies to the first acquire: once we are retrying, the
        user has already waited and a second full wait would double it.
        """
        last_error = ""
        last_daily = False
        for attempt in range(attempts):
            slot, status = await self.quota.acquire(wait=wait if attempt == 0 else 0)
            if status != "ok":
                return _Gen(status=status, error=last_error)

            try:
                resp = await self._client(
                    slot.api_name, slot.api_key
                ).aio.models.generate_content(
                    model=slot.model_name,
                    contents=contents,
                    config=config,
                )
            except Exception as e:
                if _is_rate_limited(e):
                    # Our counter disagreed with Google's. Burn the bucket for
                    # the window and try the next one rather than re-asking a
                    # key we now know is capped.
                    last_daily = _is_daily_limit(e)
                    await self.quota.mark_rate_limited(slot, daily=last_daily)
                    last_error = str(e)
                    continue
                # A transport or server error is not billed, so hand the
                # reservation back instead of quietly eating a daily request.
                await self.quota.release(slot)
                logger.error(f"gemini call failed on {slot.label}: {e}")
                return _Gen(status="error", error=str(e))

            await self.quota.charge(slot, _afc_extra_calls(resp))
            return _Gen(status="ok", text=_text_of(resp))

        # Out of attempts. If the last 429 named the daily bucket, say so --
        # reporting rpm here would skip the shutdown the handler owes admins.
        if last_daily and await self.quota.is_daily_exhausted():
            return _Gen(status="rpd", error=last_error)
        return _Gen(status="rpm", error=last_error)

    def _answer_config(self, system_instruction: str):
        from google.genai import types

        return types.GenerateContentConfig(
            temperature=self.temperature,
            system_instruction=system_instruction,
            tools=[vdb_search],
            # Cap the tool loop: each round is another billed call, and an
            # unbounded loop can drain a key on one question.
            automatic_function_calling=types.AutomaticFunctionCallingConfig(
                maximum_remote_calls=3,
            ),
        )

    def _rewrite_config(self):
        from google.genai import types

        return types.GenerateContentConfig(temperature=0.0)

    @staticmethod
    def _contents(turns: list[Turn], message: str):
        from google.genai import types

        contents = []
        for t in turns:
            contents.append(
                types.Content(role="user", parts=[types.Part(text=t.q)])
            )
            contents.append(
                types.Content(role="model", parts=[types.Part(text=t.a)])
            )
        contents.append(types.Content(role="user", parts=[types.Part(text=message)]))
        return contents

    # ------------------------------------------------------------------
    # query rewriting
    # ------------------------------------------------------------------

    async def _rewrite_query(
        self,
        question: str,
        turns: list[Turn],
        wait: int,
        template: str = REWRITE_PROMPT,
        rewrite_turns: int = 5,
    ) -> str:
        """Fold recent turns into a standalone query. Falls back to the raw
        question -- a failed rewrite should degrade retrieval, not the turn."""
        if not turns:
            return question

        history = "\n".join(
            f"User: {t.q}\nAssistant: {t.a[:200]}" for t in turns[-rewrite_turns:]
        )
        gen = await self._generate(
            self._contents([], template.format(history=history, question=question)),
            self._rewrite_config(),
            wait=wait,
        )
        if gen.status != "ok" or not gen.text:
            if gen.status != "ok":
                logger.warning(f"rewrite skipped ({gen.status}): {gen.error}")
            return question
        return gen.text.strip().strip('"') or question

    async def rewrite_handoff(
        self,
        question: str,
        borrowed: list[Turn],
        wait: int = 0,
    ) -> str:
        """Rewrite a reply written against someone else's thread into a
        self-contained question, so it can start the replier's own thread
        without dragging the other user's history along."""
        return await self._rewrite_query(
            question,
            borrowed,
            wait=wait,
            template=HANDOFF_REWRITE_PROMPT,
            rewrite_turns=len(borrowed) or 1,
        )

    # ------------------------------------------------------------------
    # main entry point
    # ------------------------------------------------------------------

    async def ask(
        self,
        user_id: int,
        question: str,
        max_turns: int = 10,
        history_ttl: int = 86400,
        wait: int = 25,
        handoff: list[Turn] | None = None,
    ) -> ChatResponse:
        """Answer `question` for `user_id` using their own stored history.

        `handoff` carries turns lifted from another user's thread when this
        question arrived as a reply to an answer written for someone else.
        They are used for this turn only and never written into the caller's
        history -- the rewritten question already carries what mattered.
        """
        from bot.services.lorebot.chat_redis import chat_redis

        raw = await chat_redis.get_history(user_id)
        turns = [
            Turn(t["q"], t["a"])
            for t in raw[-max_turns:]
            if isinstance(t, dict) and t.get("q") and t.get("a")
        ]

        search_query = await self._rewrite_query(question, turns, wait=wait)

        try:
            passages: list[Passage] = await self.retriever.search(
                query=search_query,
                top_k=self.top_k,
                prefetch=self.prefetch,
            )
        except Exception as e:
            logger.error(f"retrieval failed for '{search_query}': {e}")
            return ChatResponse(
                question=question,
                answer="",
                error=f"Lore search is unavailable right now: {e}",
                search_query=search_query,
                status="error",
            )

        message = (
            f"context_passages:\n{build_context(passages)}\n\n"
            f"User question:\n{question}\n\n"
        )

        system_instruction = SYSTEM_PROMPT
        if handoff:
            borrowed = "\n".join(f"User: {t.q}\nAssistant: {t.a[:400]}" for t in handoff)
            system_instruction = (
                f"{SYSTEM_PROMPT}\n\n"
                "This question arrived as a reply to an answer written for a "
                "different user. Their exchange is below for reference only -- "
                "ground your answer in the context passages, not in it.\n"
                f"{borrowed}"
            )

        gen = await self._generate(
            self._contents(turns, message),
            self._answer_config(system_instruction),
            wait=wait,
        )

        if gen.status != "ok":
            return ChatResponse(
                question=question,
                answer="",
                error=gen.error or gen.status,
                search_query=search_query,
                status=gen.status,
            )

        if not gen.text:
            return ChatResponse(
                question=question,
                answer="",
                error="The model returned an empty answer.",
                search_query=search_query,
                status="error",
            )

        await chat_redis.append_turn(
            user_id, question, gen.text, max_turns=max_turns, ttl=history_ttl
        )
        return ChatResponse(
            question=question,
            answer=gen.text,
            search_query=search_query,
            status="ok",
        )
