from typing import List
import chromadb
from chromadb.config import Settings as ChromaSettings
from openai import AsyncOpenAI
from config.settings import settings
import uuid
import os

os.makedirs(settings.CHROMA_PATH, exist_ok=True)

_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY, base_url=settings.OPENAI_BASE_URL)
_chroma = chromadb.PersistentClient(path=settings.CHROMA_PATH, settings=ChromaSettings(anonymized_telemetry=False))
_collection = _chroma.get_or_create_collection(name="obra_memory", metadata={"hnsw:space": "cosine"})


async def _embed(texts: List[str]) -> List[List[float]]:
    resp = await _client.embeddings.create(model=settings.EMBEDDING_MODEL, input=texts)
    return [item.embedding for item in resp.data]


async def add_memory(user_id: int, text: str, metadata: dict = None):
    emb = await _embed([text])
    mid = str(uuid.uuid4())
    meta = {"user_id": str(user_id), **(metadata or {})}
    _collection.add(ids=[mid], embeddings=emb, documents=[text], metadatas=[meta])
    return mid


async def search_memory(user_id: int, query: str, n: int = 5) -> List[str]:
    emb = await _embed([query])
    results = _collection.query(query_embeddings=emb, n_results=n, where={"user_id": str(user_id)})
    return (results.get("documents") or [[]])[0] or []


async def clear_user_vectors(user_id: int):
    try:
        existing = _collection.get(where={"user_id": str(user_id)})
        if existing and existing["ids"]:
            _collection.delete(ids=existing["ids"])
    except Exception:
        pass


async def add_group_memory(chat_id: int, text: str, metadata: dict = None):
    emb = await _embed([text])
    mid = str(uuid.uuid4())
    meta = {"scope": "group", "chat_id": str(chat_id), **(metadata or {})}
    _collection.add(ids=[mid], embeddings=emb, documents=[text], metadatas=[meta])
    return mid


async def search_group_memory(chat_id: int, query: str, n: int = 5):
    emb = await _embed([query])
    results = _collection.query(
        query_embeddings=emb,
        n_results=n,
        where={"$and": [{"scope": "group"}, {"chat_id": str(chat_id)}]},
    )
    return (results.get("documents") or [[]])[0] or []
