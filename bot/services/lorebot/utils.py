from dataclasses import dataclass , asdict
import json
import os
import aiohttp
from aiohttp.client import ClientTimeout
import asyncio

from bot.config.config import ( 
    EMBEDDING_URL as EMBED_URL , 
    QDRANT_API_KEY , 
    QDRANT_URL , 
    COLLECTION
)


@dataclass
class Passage:
    """One retrieved chunk, with its fused score."""
    rank: int
    score: float
    chunk_id: str
    page_name: str
    reference: str
    page_type: str
    content_type: str
    text: str

    def render(self) -> str:
        """Numbered form the model sees. The breadcrumb matters: it tells the
        model which page and section a claim came from, which is what makes a
        citation checkable."""
        return f"[{self.rank}] {self.reference}\n{self.text}"
    
def build_context(passages: list[Passage], budget: int = 14000) -> str:
    """
    Render passages as numbered context, stopping at the char budget.

    Truncating by whole passages rather than mid-text: a half-cut passage still
    costs tokens but can no longer be cited honestly, and a model asked to cite
    [7] should be able to see all of [7].
    """
    parts: list[str] = []
    used = 0
    for p in passages:
        block = p.render()
        if used + len(block) > budget and parts:
            break
        parts.append(block)
        used += len(block)
    return "\n\n".join(parts)


class EmbedClient:
    """Calls the HF Space. Retries because a sleeping Space cold-starts slowly."""

    def __init__(self, base_url: str = EMBED_URL, timeout: int = 120):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def embed_query(self, query: str, retries: int = 3) -> dict:
        last: Exception | None = None
        for attempt in range(retries):
            try:
                async with aiohttp.ClientSession() as session:
                    res= await session.post(
                        f"{self.base_url}/embed_query",
                        json={"query": query, "return_sparse": True},
                        timeout=ClientTimeout(total=self.timeout)
                    )
                    return await res.json()
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                last = exc
                if attempt < retries - 1:
                    # A cold Space can take ~60s to wake; back off rather than
                    # burning all retries in three seconds.
                    await asyncio.sleep(3 * 2**attempt)
        raise RuntimeError(
            f"Embedding service unreachable at {self.base_url}: {last}"
        ) from last

    async def health(self) -> dict:
        async with aiohttp.ClientSession() as session:
            res = await session.get(
                f"{self.base_url}/health",
                timeout=ClientTimeout(total=self.timeout)
            )
            return await res.json()
        
class Retriever:
    def __init__(
        self,
        url: str = QDRANT_URL,
        api_key: str = QDRANT_API_KEY,
        collection: str = COLLECTION,
        embedder: EmbedClient | None = None,
    ):
        from qdrant_client import AsyncQdrantClient

        self.client = AsyncQdrantClient(url=url, api_key=api_key, timeout=60)
        self.collection = collection
        self.embedder = embedder or EmbedClient()
        
    async def aclose(self) -> None:
        """Release the underlying HTTP connection pool. Call this on shutdown,
        or use the class as an async context manager instead."""
        await self.client.close()

    async def __aenter__(self) -> "Retriever":
        return self

    async def __aexit__(self, *exc) -> None:
        await self.aclose()

    async def search(
        self,
        query: str,
        top_k: int = 10,
        prefetch: int = 60,
        page_name: str | None = None,
        page_type: str | None = None,
        content_type: str | None = None,
    ) -> list[Passage]:
        from qdrant_client import models

        enc = await self.embedder.embed_query(query)

        must = []
        if page_type:
            must.append(models.FieldCondition(
                key="page_type", match=models.MatchValue(value=page_type)))
        if content_type:
            must.append(models.FieldCondition(
                key="content_type", match=models.MatchValue(value=content_type)))
        if page_name:
            must.append(models.FieldCondition(
                key="page_name", match=models.MatchValue(value=page_name)))
        flt = models.Filter(must=must) if must else None

        branches = [
            models.Prefetch(query=enc["dense"], using="dense",
                            limit=prefetch, filter=flt)
        ]
        sparse = enc.get("sparse")
        if sparse and sparse.get("indices"):
            branches.append(models.Prefetch(
                query=models.SparseVector(indices=sparse["indices"],
                                          values=sparse["values"]),
                using="sparse", limit=prefetch, filter=flt,
            ))

        result = await self.client.query_points(
            collection_name=self.collection,
            prefetch=branches,
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=top_k,
            with_payload=True,
        )
        hits = result.points

        out: list[Passage] = []
        for i, h in enumerate(hits, 1):
            p = h.payload or {}
            out.append(Passage(
                rank=i, score=float(h.score), chunk_id=p.get("chunk_id", ""),
                page_name=p.get("page_name", ""),
                reference=p.get("referenceOnPage", p.get("page_name", "?")),
                page_type=p.get("page_type", ""), content_type=p.get("content_type", ""),
                text=p.get("text", ""),
            ))
        return out

# gemini tool fuctions

_TOOL_RETRIEVER: Retriever | None = None


def _tool_retriever() -> Retriever:
    """One shared Retriever for tool calls. Building one per query leaks an
    AsyncQdrantClient (and its connection pool) on every search, which the
    chatbot now issues on most turns."""
    global _TOOL_RETRIEVER
    if _TOOL_RETRIEVER is None:
        _TOOL_RETRIEVER = Retriever()
    return _TOOL_RETRIEVER


async def close_tool_retriever() -> None:
    global _TOOL_RETRIEVER
    if _TOOL_RETRIEVER is not None:
        await _TOOL_RETRIEVER.aclose()
        _TOOL_RETRIEVER = None


async def vdb_search(
    queries: list[str],
    TOP_K: int = 5,
    PREFETCH: int = 20,
    page_name: str | None = None,
    page_type: str | None = None,
    content_type: str | None = None,
)-> list[str]:
    """
    Search the vector database for passages relevant to the given queries.
    search for pages to get all the relevant passages of the page , limit it via TOP_K and PREFETCH parameters.
    use when provided context is not enough to answer the question.

    args:
        queries: List of query strings to search for.
        TOP_K: Number of top results to return.
        PREFETCH: Number of results to prefetch for fusion.
        page_name: Optional filter for the name of the page.
        page_type: Optional filter for the type of page.
        content_type: Optional filter for the type of content.

    returns:
        List of passages as dictionaries, each containing rank, score, chunk_id, page_name, reference, page_type, content_type, and text.

    """
    retriever = _tool_retriever()
    t=[]
    for q in queries:
        t.append(
            retriever.search(
                query=q,
                top_k=TOP_K,
                prefetch=PREFETCH,
                page_name=page_name,
                page_type=page_type,
                content_type=content_type
            )
        )
    # one bad query should not sink the whole tool call
    t=await asyncio.gather(*t, return_exceptions=True)
    passages = []
    for r in t:
        if isinstance(r, BaseException):
            print(f"vdb_search branch failed: {r}")
            continue
        passages.append(build_context(r))
    return passages