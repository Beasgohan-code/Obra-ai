import aiosqlite
import json
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from config.settings import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    chat_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_conv_chat ON conversations(chat_id);

CREATE TABLE IF NOT EXISTS user_memory (
    user_id INTEGER PRIMARY KEY,
    name TEXT,
    preferences TEXT,
    notes TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS chat_meta (
    chat_id INTEGER PRIMARY KEY,
    title TEXT,
    is_group INTEGER DEFAULT 0,
    last_active TEXT
);

CREATE TABLE IF NOT EXISTS rate_limits (
    user_id INTEGER NOT NULL,
    ts TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rl_user ON rate_limits(user_id);

CREATE TABLE IF NOT EXISTS usage_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    chat_id INTEGER,
    event TEXT,
    meta TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS blocked_users (
    user_id INTEGER PRIMARY KEY,
    reason TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS daily_usage (
    user_id INTEGER NOT NULL,
    day TEXT NOT NULL,
    count INTEGER DEFAULT 0,
    PRIMARY KEY (user_id, day)
);

CREATE TABLE IF NOT EXISTS user_skills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    instruction TEXT NOT NULL,
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_skills_user ON user_skills(user_id);

CREATE TABLE IF NOT EXISTS user_settings (
    user_id INTEGER PRIMARY KEY,
    language TEXT DEFAULT 'en',
    api_key TEXT,
    api_base TEXT,
    api_model TEXT,
    tts_enabled INTEGER DEFAULT 0,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    chat_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_proj_user ON projects(user_id);

CREATE TABLE IF NOT EXISTS business_connections (
  connection_id TEXT PRIMARY KEY,
  user_id INTEGER,
  is_enabled INTEGER DEFAULT 1,
  can_reply INTEGER DEFAULT 1,
  raw TEXT DEFAULT '{}',
  updated_at TEXT
);
CREATE TABLE IF NOT EXISTS pending_actions (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    chat_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at TEXT
);
"""


class Database:
    def __init__(self, path: str = None):
        self.path = path or settings.DB_PATH

    async def init(self):
        async with aiosqlite.connect(self.path) as db:
            await db.executescript(SCHEMA)
            await db.commit()

    async def add_message(self, chat_id: int, role: str, content: str):
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT INTO conversations (chat_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                (chat_id, role, content, datetime.utcnow().isoformat()),
            )
            await db.commit()

    async def get_history(self, chat_id: int, limit: int = 40) -> List[Dict[str, str]]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT role, content FROM conversations WHERE chat_id=? ORDER BY created_at DESC LIMIT ?",
                (chat_id, limit),
            )
            rows = await cur.fetchall()
            return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    async def clear_history(self, chat_id: int):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("DELETE FROM conversations WHERE chat_id=?", (chat_id,))
            await db.commit()

    async def set_user_memory(self, user_id: int, name=None, preferences=None, notes=None):
        async with aiosqlite.connect(self.path) as db:
            existing = await self.get_user_memory(user_id)
            name = name or (existing or {}).get("name")
            prefs = preferences if preferences is not None else (existing or {}).get("preferences", {})
            notes = notes if notes is not None else (existing or {}).get("notes", "")
            await db.execute(
                """INSERT INTO user_memory (user_id, name, preferences, notes, updated_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(user_id) DO UPDATE SET
                     name=excluded.name, preferences=excluded.preferences,
                     notes=excluded.notes, updated_at=excluded.updated_at""",
                (user_id, name, json.dumps(prefs or {}), notes or "", datetime.utcnow().isoformat()),
            )
            await db.commit()

    async def set_memory_kv(self, user_id: int, key: str, value: str):
        mem = await self.get_user_memory(user_id) or {}
        prefs = mem.get("preferences") or {}
        if not isinstance(prefs, dict):
            prefs = {}
        prefs[str(key)] = str(value)
        await self.set_user_memory(user_id, preferences=prefs)
        return True

    async def get_user_memory(self, user_id: int) -> Optional[Dict[str, Any]]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM user_memory WHERE user_id=?", (user_id,))
            row = await cur.fetchone()
            if not row:
                return None
            return {
                "user_id": row["user_id"],
                "name": row["name"],
                "preferences": json.loads(row["preferences"] or "{}"),
                "notes": row["notes"] or "",
                "updated_at": row["updated_at"],
            }

    async def update_chat_meta(self, chat_id: int, title=None, is_group=False):
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """INSERT INTO chat_meta (chat_id, title, is_group, last_active)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(chat_id) DO UPDATE SET
                     title=COALESCE(excluded.title, chat_meta.title),
                     is_group=excluded.is_group, last_active=excluded.last_active""",
                (chat_id, title, 1 if is_group else 0, datetime.utcnow().isoformat()),
            )
            await db.commit()

    # ---------- Rate limit ----------
    async def check_rate_limit(self, user_id: int) -> tuple[bool, int]:
        """Returns (allowed, remaining)."""
        window = settings.RATE_LIMIT_WINDOW_SECONDS
        limit = settings.RATE_LIMIT_MESSAGES
        cutoff = (datetime.utcnow() - timedelta(seconds=window)).isoformat()
        async with aiosqlite.connect(self.path) as db:
            await db.execute("DELETE FROM rate_limits WHERE ts < ?", (cutoff,))
            cur = await db.execute(
                "SELECT COUNT(*) FROM rate_limits WHERE user_id=?", (user_id,)
            )
            count = (await cur.fetchone())[0]
            if count >= limit:
                return False, 0
            await db.execute(
                "INSERT INTO rate_limits (user_id, ts) VALUES (?, ?)",
                (user_id, datetime.utcnow().isoformat()),
            )
            await db.commit()
            return True, limit - count - 1

    # ---------- Stats & admin ----------
    async def log_event(self, user_id: int, chat_id: int, event: str, meta: dict = None):
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT INTO usage_stats (user_id, chat_id, event, meta, created_at) VALUES (?,?,?,?,?)",
                (user_id, chat_id, event, json.dumps(meta or {}), datetime.utcnow().isoformat()),
            )
            await db.commit()

    async def get_stats(self, hours: int = 24) -> Dict[str, Any]:
        cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT event, COUNT(*) as c FROM usage_stats WHERE created_at>? GROUP BY event",
                (cutoff,),
            )
            events = {r["event"]: r["c"] for r in await cur.fetchall()}
            cur = await db.execute(
                "SELECT COUNT(DISTINCT user_id) FROM usage_stats WHERE created_at>?", (cutoff,)
            )
            users = (await cur.fetchone())[0]
            cur = await db.execute("SELECT COUNT(*) FROM blocked_users")
            blocked = (await cur.fetchone())[0]
            cur = await db.execute("SELECT COUNT(*) FROM chat_meta")
            chats = (await cur.fetchone())[0]
            return {"events": events, "active_users": users, "blocked": blocked, "chats": chats, "hours": hours}

    async def block_user(self, user_id: int, reason: str = ""):
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO blocked_users (user_id, reason, created_at) VALUES (?,?,?)",
                (user_id, reason, datetime.utcnow().isoformat()),
            )
            await db.commit()

    async def unblock_user(self, user_id: int):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("DELETE FROM blocked_users WHERE user_id=?", (user_id,))
            await db.commit()

    async def is_blocked(self, user_id: int) -> bool:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute("SELECT 1 FROM blocked_users WHERE user_id=?", (user_id,))
            return await cur.fetchone() is not None

    # ---------- Daily quota ----------
    async def check_daily_quota(self, user_id: int) -> tuple[bool, int]:
        """Returns (allowed, remaining). DAILY_QUOTA=0 means unlimited."""
        quota = settings.DAILY_QUOTA
        if quota <= 0:
            return True, -1
        day = datetime.utcnow().strftime("%Y-%m-%d")
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "SELECT count FROM daily_usage WHERE user_id=? AND day=?",
                (user_id, day),
            )
            row = await cur.fetchone()
            count = row[0] if row else 0
            if count >= quota:
                return False, 0
            if row:
                await db.execute(
                    "UPDATE daily_usage SET count=count+1 WHERE user_id=? AND day=?",
                    (user_id, day),
                )
            else:
                await db.execute(
                    "INSERT INTO daily_usage (user_id, day, count) VALUES (?,?,1)",
                    (user_id, day),
                )
            await db.commit()
            return True, quota - count - 1

    async def get_daily_usage(self, user_id: int) -> int:
        day = datetime.utcnow().strftime("%Y-%m-%d")
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "SELECT count FROM daily_usage WHERE user_id=? AND day=?",
                (user_id, day),
            )
            row = await cur.fetchone()
            return row[0] if row else 0


    async def add_skill(self, user_id: int, name: str, instruction: str):
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT INTO user_skills (user_id, name, instruction, created_at) VALUES (?,?,?,?)",
                (user_id, name, instruction, datetime.utcnow().isoformat()),
            )
            await db.commit()

    async def list_skills(self, user_id: int):
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT id, name, instruction, created_at FROM user_skills WHERE user_id=? ORDER BY id DESC",
                (user_id,),
            )
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def delete_skill(self, user_id: int, skill_id: int):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("DELETE FROM user_skills WHERE user_id=? AND id=?", (user_id, skill_id))
            await db.commit()

    async def get_user_settings(self, user_id: int) -> dict:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM user_settings WHERE user_id=?", (user_id,))
            row = await cur.fetchone()
            if not row:
                return {"user_id": user_id, "language": "en", "api_key": None, "api_base": None, "api_model": None, "tts_enabled": 0}
            return dict(row)

    async def set_user_settings(self, user_id: int, **kwargs):
        cur = await self.get_user_settings(user_id)
        cur.update({k: v for k, v in kwargs.items() if v is not None})
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """INSERT INTO user_settings (user_id, language, api_key, api_base, api_model, tts_enabled, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(user_id) DO UPDATE SET
                     language=excluded.language, api_key=excluded.api_key, api_base=excluded.api_base,
                     api_model=excluded.api_model, tts_enabled=excluded.tts_enabled, updated_at=excluded.updated_at""",
                (user_id, cur.get("language") or "en", cur.get("api_key"), cur.get("api_base"),
                 cur.get("api_model"), int(cur.get("tts_enabled") or 0), datetime.utcnow().isoformat()),
            )
            await db.commit()

    async def set_project_title(self, user_id: int, chat_id: int, title: str):
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT INTO projects (user_id, chat_id, title, created_at) VALUES (?,?,?,?)",
                (user_id, chat_id, title[:120], datetime.utcnow().isoformat()),
            )
            await db.commit()

    async def list_projects(self, user_id: int, limit: int = 20):
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM projects WHERE user_id=? ORDER BY id DESC LIMIT ?",
                (user_id, limit),
            )
            return [dict(r) for r in await cur.fetchall()]

    async def save_pending(self, pid: str, user_id: int, chat_id: int, action: str, payload: dict):
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO pending_actions (id, user_id, chat_id, action, payload, created_at) VALUES (?,?,?,?,?,?)",
                (pid, user_id, chat_id, action, json.dumps(payload), datetime.utcnow().isoformat()),
            )
            await db.commit()

    async def pop_pending(self, pid: str):
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM pending_actions WHERE id=?", (pid,))
            row = await cur.fetchone()
            if row:
                await db.execute("DELETE FROM pending_actions WHERE id=?", (pid,))
                await db.commit()
                d = dict(row)
                d["payload"] = json.loads(d["payload"])
                return d
            return None


    async def save_business_connection(self, connection_id: str, user_id: int, is_enabled: bool = True, can_reply: bool = True, raw: dict = None):
        import json
        from datetime import datetime
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """INSERT INTO business_connections (connection_id, user_id, is_enabled, can_reply, raw, updated_at)
                   VALUES (?,?,?,?,?,?)
                   ON CONFLICT(connection_id) DO UPDATE SET
                     user_id=excluded.user_id, is_enabled=excluded.is_enabled,
                     can_reply=excluded.can_reply, raw=excluded.raw, updated_at=excluded.updated_at""",
                (connection_id, user_id, 1 if is_enabled else 0, 1 if can_reply else 0,
                 json.dumps(raw or {}), datetime.utcnow().isoformat()),
            )
            await db.commit()

    async def get_business_connection(self, connection_id: str):
        import json
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM business_connections WHERE connection_id=?", (connection_id,))
            row = await cur.fetchone()
            if not row:
                return None
            return {
                "connection_id": row["connection_id"],
                "user_id": row["user_id"],
                "is_enabled": bool(row["is_enabled"]),
                "can_reply": bool(row["can_reply"]),
                "raw": json.loads(row["raw"] or "{}"),
            }


db = Database()
