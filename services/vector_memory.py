"""Vector memory for obra.

Design goals (fixes "bot won't start / memory silently broken"):
- chromadb is imported LAZILY — if it is missing or fails to initialise, the bot
  still runs and falls back to a sqlite keyword store (services.db).
- Embeddings try every configured LLM provider (settings.provider_chain()) and
  finally fall back to a deterministic local hashed embedding, so memory works
  even with a chat-only API key and zero extra dependencies.
"""
from __future__ import annotations

import hashlib
import logging
import math
import os
import re
import uuid
from typing import List, Optional

from openai import AsyncOpenAI

from config.settings import settings
from services.db import db

logger = logging.getLogger("obra.memory")

# ---------------------------------------------------------------- chroma (lazy)
_collection = None
_chroma_failed = False


def _get_collection():
    """Return the chroma collection, or None if chromadb is unavailable."""
    global _collection, _chroma_failed
    if _collection is not None or _chroma_failed:
        return _collection
    try:
        import chromadb
        from chromadb.config import Settings as ChromaSettings
        os.makedirs(settings.CHROMA_PATH, exist_ok=True)
        client = chromadb.PersistentClient(
            path=settings.CHROMA_PATH,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        _collection = client.get_or_create_collection(
            name="obra_memory", metadata={"hnsw:space": "cosine"}
        )
        logger.info("chromadb memory ready at %s", settings.CHROMA_PATH)
    except Exception as e:
        logger.warning("chromadb unavailable (%s) — using sqlite keyword memory", e)
        _chroma_failed = True
        _collection = None
    return _collection


# ---------------------------------------------------------------- embeddings
_embed_client: Optional[AsyncOpenAI] = None
_embed_base: Optional[str] = None


async def _embed_via_provider(texts: List[str]) -> Optional[List[List[float]]]:
    """Try each configured provider's embeddings endpoint until one works."""
    global _embed_client, _embed_base
    chain = settings.provider_chain()
    # reuse a known-good client first
    candidates = []
    if _embed_client is not None and _embed_base:
        candidates.append((_embed_base, _embed_client))
    for prov in chain:
        if _embed_base and prov["base_url"] == _embed_base:
            continue
        candidates.append((prov["base_url"], None))

    for base_url, client in candidates:
        try:
            if client is None:
                prov = next(p for p in chain if p["base_url"] == base_url)
                client = AsyncOpenAI(api_key=prov["api_key"], base_url=base_url, timeout=30.0)
            resp = await client.embeddings.create(model=settings.EMBEDDING_MODEL, input=texts)
            _embed_client, _embed_base = client, base_url
            return [item.embedding for item in resp.data]
        except Exception as e:
            logger.debug("embeddings via %s failed: %s", base_url, str(e)[:120])
    return None


_EMB_DIM = 384


def _local_embed(texts: List[str]) -> List[List[float]]:
    """Deterministic hashed bag-of-words embedding (no network, no deps)."""
    out = []
    for text in texts:
        vec = [0.0] * _EMB_DIM
        for tok in re.findall(r"\w+", (text or "").lower()):
            h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
            vec[h % _EMB_DIM] += 1.0
            # bigram for a little word-order signal
            h2 = int(hashlib.md5(("_" + tok).encode("utf-8")).hexdigest(), 16)
            vec[h2 % _EMB_DIM] += 0.5
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        out.append([v / norm for v in vec])
    return out


async def _embed(texts: List[str]) -> List[List[float]]:
    emb = await _embed_via_provider(texts)
    if emb is not None:
        return emb
    return _local_embed(texts)


# ---------------------------------------------------------------- public API
async def add_memory(user_id: int, text: str, metadata: dict = None):
    col = _get_collection()
    if col is None:
        await db.add_semantic_memory("user", user_id, text, metadata)
        return None
    try:
        emb = await _embed([text])
        mid = str(uuid.uuid4())
        meta = {"user_id": str(user_id), **(metadata or {})}
        col.add(ids=[mid], embeddings=emb, documents=[text], metadatas=[meta])
        return mid
    except Exception as e:
        logger.warning("add_memory (chroma) failed, using sqlite fallback: %s", e)
        await db.add_semantic_memory("user", user_id, text, metadata)
        return None


async def search_memory(user_id: int, query: str, n: int = 5) -> List[str]:
    col = _get_collection()
    if col is None:
        return await db.search_semantic_memory("user", user_id, query, n)
    try:
        emb = await _embed([query])
        results = col.query(query_embeddings=emb, n_results=n, where={"user_id": str(user_id)})
        return (results.get("documents") or [[]])[0] or []
    except Exception as e:
        logger.warning("search_memory (chroma) failed, using sqlite fallback: %s", e)
        return await db.search_semantic_memory("user", user_id, query, n)


async def clear_user_vectors(user_id: int):
    col = _get_collection()
    if col is None:
        await db.clear_semantic_memory("user", user_id)
        return
    try:
        existing = col.get(where={"user_id": str(user_id)})
        if existing and existing.get("ids"):
            col.delete(ids=existing["ids"])
    except Exception as e:
        logger.warning("clear_user_vectors: %s", e)
    await db.clear_semantic_memory("user", user_id)


async def add_group_memory(chat_id: int, text: str, metadata: dict = None):
    col = _get_collection()
    if col is None:
        await db.add_semantic_memory("group", chat_id, text, metadata)
        return None
    try:
        emb = await _embed([text])
        mid = str(uuid.uuid4())
        meta = {"scope": "group", "chat_id": str(chat_id), **(metadata or {})}
        col.add(ids=[mid], embeddings=emb, documents=[text], metadatas=[meta])
        return mid
    except Exception as e:
        logger.warning("add_group_memory (chroma) failed, using sqlite fallback: %s", e)
        await db.add_semantic_memory("group", chat_id, text, metadata)
        return None


async def search_group_memory(chat_id: int, query: str, n: int = 5) -> List[str]:
    col = _get_collection()
    if col is None:
        return await db.search_semantic_memory("group", chat_id, query, n)
    try:
        emb = await _embed([query])
        results = col.query(
            query_embeddings=emb,
            n_results=n,
            where={"$and": [{"scope": "group"}, {"chat_id": str(chat_id)}]},
        )
        return (results.get("documents") or [[]])[0] or []
    except Exception as e:
        logger.warning("search_group_memory (chroma) failed, using sqlite fallback: %s", e)
        return await db.search_semantic_memory("group", chat_id, query, n)
