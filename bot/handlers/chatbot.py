from aiogram import Router, F, Bot
from aiogram.types import Message
from aiogram.filters import Command, CommandObject
from aiogram.dispatcher.event.bases import SkipHandler
import html
import logging
import re

from bot.config.config import users_record, cmdavailability
from bot.services.lorebot.chat import Turn
from bot.services.lorebot.chat_redis import chat_redis
from bot.services.lorebot.spoiler import apply_spoiler, spoiler_enabled
from bot.services.lorebot.runtime import (
    chat_bot,
    settings,
    quota_manager,
    on_rpd_exhausted,
    take_user_slot,
    user_usage,
)

rt = Router()
logger = logging.getLogger(__name__)

THINKING = "🔮 Consulting the archives..."

NOT_REGISTERED = (
    "Please link your account first with /login <UID> to use the lore chatbot."
)

GROUP_TYPES = ("group", "supergroup")


def _user_cap_text(cap: int) -> str:
    return (
        f"You've used all {cap} of your lore questions for today.\n"
        "Your allowance resets at midnight PT — see you then!"
    )


async def _ask_allowed_here(msg: Message) -> bool:
    """Group admins can switch /ask off for their group via /group_settings.

    Only consulted in groups; a DM has no admins to set a policy.
    """
    if msg.chat.type not in GROUP_TYPES:
        return True
    try:
        from bot.DB.asyncsessions import session_factory
        from bot.DB.repo.group_settings_repo import GroupCommandSettingsRepo

        async with session_factory() as session:
            state = await GroupCommandSettingsRepo(session).is_enabled(
                msg.chat.id, "ask"
            )
    except Exception as e:
        logger.error(f"failed to read group settings for {msg.chat.id}: {e}")
        return True
    # None means the group never chose, so the bot-wide default applies
    return True if state is None else state


def _busy_text(status: str) -> str:
    if status == "empty":
        return (
            "The lore chatbot has no API keys configured yet. "
            "Ask a bot admin to add one."
        )
    if status == "rpd":
        return (
            "The lore chatbot has used up today's request quota. "
            "It comes back online after the next reset."
        )
    return (
        "The lore chatbot is handling too many questions right now. "
        "Give it a few seconds and try again."
    )


CHUNK_LIMIT = 3900


def _split(text: str) -> list[str]:
    """Break an over-long answer on line boundaries.

    Telegram's cap is 4096. Splitting on newlines keeps most inline HTML
    balanced; anything that still breaks falls back to plain text at send
    time, which is why this does not try to be a real HTML-aware splitter.
    """
    if len(text) <= CHUNK_LIMIT:
        return [text]

    parts: list[str] = []
    buf = ""
    for line in text.split("\n"):
        while len(line) > CHUNK_LIMIT:
            if buf:
                parts.append(buf)
                buf = ""
            parts.append(line[:CHUNK_LIMIT])
            line = line[CHUNK_LIMIT:]
        if len(buf) + len(line) + 1 > CHUNK_LIMIT:
            parts.append(buf)
            buf = line
        else:
            buf = f"{buf}\n{line}" if buf else line
    if buf:
        parts.append(buf)
    return parts


async def _deliver(
    placeholder: Message | None,
    msg: Message,
    text: str,
    spoiler: bool = False,
) -> list[Message]:
    """Land the answer in the placeholder if we have one, else as a new reply.

    Telegram rejects HTML the model got slightly wrong and caps messages at
    4096 chars, so this falls back to plain text and splits long answers --
    losing formatting beats losing the answer.
    """
    # Split first, then wrap: a spoiler tag cannot span two messages, so each
    # chunk carries its own pair.
    chunks = [apply_spoiler(c, spoiler) for c in _split(text)]
    sent: list[Message] = []

    first = None
    if placeholder:
        first = await _edit(placeholder, chunks[0])
    if first is None:
        first = await _reply(msg, chunks[0])
    if first is not None:
        sent.append(first)

    for chunk in chunks[1:]:
        try:
            sent.append(await msg.answer(chunk, parse_mode="HTML"))
        except Exception as e:
            logger.warning(f"HTML continuation failed, sending plain: {e}")
            try:
                sent.append(await msg.answer(_plain(chunk), parse_mode=None))
            except Exception as e2:
                logger.error(f"failed to send answer continuation: {e2}")
                break
    return sent


def _plain(text: str) -> str:
    """Readable text for the no-parse-mode fallback.

    Without this the fallback prints the markup it failed to parse, tags and
    all. Spoilers cannot survive here -- plain text has no way to hide
    anything -- so the answer arrives visible rather than not at all.
    """
    stripped = re.sub(r"<[^>]+>", "", text)
    return html.unescape(stripped)


async def _edit(placeholder: Message, text: str) -> Message | None:
    for mode in ("HTML", None):
        body = text if mode else _plain(text)
        try:
            res = await placeholder.edit_text(body, parse_mode=mode)
            # edit_text returns True only for inline messages; ours is a real
            # message, but normalise so callers always get something with ids
            return res if isinstance(res, Message) else placeholder
        except Exception as e:
            logger.warning(f"edit as {mode or 'plain'} failed: {e}")
    return None


async def _reply(msg: Message, text: str) -> Message | None:
    for mode in ("HTML", None):
        body = text if mode else _plain(text)
        try:
            return await msg.reply(body, parse_mode=mode)
        except Exception as e:
            logger.warning(f"reply as {mode or 'plain'} failed: {e}")
    return None


async def _fail(placeholder: Message | None, msg: Message, text: str) -> None:
    if placeholder:
        try:
            await placeholder.edit_text(text, parse_mode=None)
            return
        except Exception:
            pass
    await msg.reply(text, parse_mode=None)


async def _answer(
    msg: Message,
    user_id: int,
    question: str,
    handoff: list[Turn] | None = None,
) -> None:
    """Shared path for /ask and reply-triggered questions."""
    placeholder: Message | None = None
    try:
        placeholder = await msg.reply(THINKING, parse_mode=None)
    except Exception as e:
        logger.warning(f"could not post placeholder: {e}")

    res = await chat_bot.ask(
        user_id=user_id,
        question=question,
        max_turns=settings["max_turns"],
        history_ttl=settings["history_ttl"],
        wait=settings["rpm_wait"],
        handoff=handoff,
    )

    spoiler = await spoiler_enabled(msg.chat.id, msg.chat.type in GROUP_TYPES)

    if res.status == "rpd":
        # Every bucket is out for the day: warn admins and take /ask offline.
        await on_rpd_exhausted()
        await _fail(placeholder, msg, _busy_text("rpd"))
        return

    if res.status in ("rpm", "empty"):
        await _fail(placeholder, msg, _busy_text(res.status))
        return

    if res.status != "ok" or not res.answer:
        logger.error(f"lore answer failed for {user_id}: {res.error}")
        await _fail(
            placeholder, msg,
            "Something went wrong answering that. Please try again.",
        )
        return

    sent = await _deliver(placeholder, msg, res.answer, spoiler=spoiler)
    if not sent:
        logger.error(f"could not deliver lore answer to {user_id}")
        return

    # Make the answer replyable for a while -- every chunk, so a reply to any
    # part of a long answer continues the thread. The TTL is the feature:
    # past it, a reply to it is an ordinary message again.
    for part in sent:
        await chat_redis.remember_answer(
            chat_id=part.chat.id,
            msg_id=part.message_id,
            owner_id=user_id,
            ttl=settings["reply_ttl"],
        )
    logger.info(
        f"lore answer | user={user_id} chat={msg.chat.id} "
        f"q={res.question[:80]!r} search={res.search_query!r}"
    )


@rt.message(Command("ask"))
async def ask(msg: Message, command: CommandObject):
    if not msg.from_user:
        return
    tele_id = msg.from_user.id

    if not users_record.is_registered(tele_id):
        await msg.reply(NOT_REGISTERED, parse_mode=None)
        return

    # command.args handles /ask@BotName in groups; falling back to the replied
    # message lets "reply + /ask" work as a way to ask about quoted text.
    question = (command.args or "").strip()
    if not question and msg.reply_to_message:
        question = (msg.reply_to_message.text or "").strip()

    if not question:
        await msg.reply(
            "Ask me something about Honkai: Star Rail lore.\n"
            "Example: /ask who is Acheron\n\n"
            "You can also reply to my answers to keep the conversation going.",
            parse_mode=None,
        )
        return

    limit = settings["max_question_len"]
    if len(question) > limit:
        await msg.reply(
            f"That question is too long. Please keep it under {limit} characters.",
            parse_mode=None,
        )
        return

    if not await _ask_allowed_here(msg):
        await msg.reply(
            "The lore chatbot is switched off in this group. "
            "A group admin can turn it back on with /group_settings.",
            parse_mode=None,
        )
        return

    # Charged last, so a rejected question never costs the asker an allowance.
    allowed, _used, cap = await take_user_slot(tele_id)
    if not allowed:
        await msg.reply(_user_cap_text(cap), parse_mode=None)
        return

    await _answer(msg, tele_id, question)


@rt.message(
    F.text,
    ~F.text.startswith("/"),
    F.reply_to_message.from_user.is_bot.is_(True),
)
async def reply_to_answer(msg: Message, bot: Bot):
    """Continue a conversation by replying to one of the bot's answers.

    Same user  -> straight follow-up; their thread already holds the context.
    Other user -> lift the last few turns of the original thread, rewrite the
    reply into a standalone question, then run it in the replier's OWN thread.
    Nothing is written back into the original user's history.

    Every non-lore path raises SkipHandler rather than returning: this router
    sits ahead of the catch-all in handlers/groups.py, and a handler that
    matches and returns would stop propagation, silently killing the
    user/group cache updates for every reply message in the bot.
    """
    target = msg.reply_to_message
    me = await bot.me()
    if not target or not target.from_user or target.from_user.id != me.id:
        raise SkipHandler()

    owner_id = await chat_redis.get_answer_owner(msg.chat.id, target.message_id)
    if owner_id is None:
        # Replying to some other bot message, or the reply window expired.
        raise SkipHandler()

    if not msg.from_user:
        raise SkipHandler()
    tele_id = msg.from_user.id

    if not users_record.is_registered(tele_id):
        await msg.reply(NOT_REGISTERED, parse_mode=None)
        return

    # No CommandObject on this path, so CommandChecker cannot gate it -- the
    # RPD kill-switch has to be honoured explicitly.
    if not cmdavailability.is_enabled("ask"):
        await msg.reply(_busy_text("rpd"), parse_mode=None)
        return

    question = (msg.text or "").strip()
    if not question:
        raise SkipHandler()

    limit = settings["max_question_len"]
    if len(question) > limit:
        await msg.reply(
            f"That question is too long. Please keep it under {limit} characters.",
            parse_mode=None,
        )
        return

    if not await _ask_allowed_here(msg):
        raise SkipHandler()

    allowed, _used, cap = await take_user_slot(tele_id)
    if not allowed:
        await msg.reply(_user_cap_text(cap), parse_mode=None)
        return

    if owner_id == tele_id:
        await _answer(msg, tele_id, question)
        return

    borrowed_raw = await chat_redis.get_history(owner_id)
    borrowed = [
        Turn(t["q"], t["a"])
        for t in borrowed_raw[-settings["handoff_turns"]:]
        if isinstance(t, dict) and t.get("q") and t.get("a")
    ]

    if not borrowed:
        # That thread expired, so there is nothing to inherit -- treat it as
        # a fresh question of this user's own.
        await _answer(msg, tele_id, question)
        return

    rewritten = await chat_bot.rewrite_handoff(question, borrowed, wait=0)
    if rewritten != question:
        logger.info(
            f"lore handoff | replier={tele_id} owner={owner_id} "
            f"raw={question[:60]!r} rewritten={rewritten[:80]!r}"
        )

    await _answer(msg, tele_id, rewritten, handoff=borrowed)


@rt.message(Command("ask_reset"))
async def ask_reset(msg: Message):
    """Forget the caller's conversation and start fresh."""
    if not msg.from_user:
        return
    cleared = await chat_redis.clear_history(msg.from_user.id)
    await msg.reply(
        "Your lore conversation has been reset." if cleared
        else "You don't have an active lore conversation.",
        parse_mode=None,
    )


@rt.message(Command("ask_status"))
async def ask_status(msg: Message):
    """How much of the caller's memory is in use, and whether the pool is up."""
    if not msg.from_user:
        return
    tele_id = msg.from_user.id
    turns = await chat_redis.history_len(tele_id)
    rows = await quota_manager.usage()
    rpd_used = sum(r["rpd_used"] for r in rows)
    rpd_cap = sum(r["rpd"] for r in rows)
    user_used, user_cap = await user_usage(tele_id)

    await msg.reply(
        "<b>Your lore chat</b>\n"
        f"Remembered turns: {turns}/{settings['max_turns']}\n"
        f"My answers stay replyable for {settings['reply_ttl'] // 60} min\n"
        f"Questions today: {user_used}/{user_cap}\n\n"
        "<b>Service</b>\n"
        f"Requests used today: {rpd_used}/{rpd_cap}",
        parse_mode="HTML",
    )
