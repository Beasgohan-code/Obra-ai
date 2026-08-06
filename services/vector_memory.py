"""Optional Chroma vector memory — no-op if chromadb missing."""
from __future__ import annotations
import logging
logger = logging.getLogger("obra.vec")
_ok = False
try:
    import chromadb
    from chromadb.config import Settings as CS
    from config.settings import settings
    _client = chromadb.PersistentClient(path=settings.CHROMA_PATH, settings=CS(anonymized_telemetry=False))
    _collection = _client.get_or_create_collection("obra_mem")
    _ok = True
except Exception as e:
    logger.warning("vector memory disabled: %s", e)

async def add_memory(user_id, text, metadata=None):
    if not _ok: return None
    import uuid
    mid = str(uuid.uuid4())
    meta = {"user_id": str(user_id), **(metadata or {})}
    _collection.add(ids=[mid], documents=[text], metadatas=[meta])
    return mid

async def search_memory(user_id, query, n=5):
    if not _ok: return []
    try:
        r = _collection.query(query_texts=[query], n_results=n, where={"user_id": str(user_id)})
        return (r.get("documents") or [[]])[0] or []
    except Exception:
        return []

async def add_group_memory(chat_id, text, metadata=None):
    if not _ok: return None
    import uuid
    mid = str(uuid.uuid4())
    meta = {"scope":"group","chat_id":str(chat_id), **(metadata or {})}
    _collection.add(ids=[mid], documents=[text], metadatas=[meta])
    return mid

async def search_group_memory(chat_id, query, n=5):
    if not _ok: return []
    try:
        r = _collection.query(query_texts=[query], n_results=n, where={"$and":[{"scope":"group"},{"chat_id":str(chat_id)}]})
        return (r.get("documents") or [[]])[0] or []
    except Exception:
        return []

async def clear_user(user_id):
    pass
