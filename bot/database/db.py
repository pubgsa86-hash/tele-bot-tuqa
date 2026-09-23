import os

import aiosqlite

from bot.utils.helpers import ensure_dir, iso_now


class Database:
    def __init__(self, path):
        self.path = path
        self._conn = None
        self._lock = None

    async def init(self):
        ensure_dir(os.path.dirname(self.path) or ".")
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL;")
        await self._conn.execute("PRAGMA busy_timeout=5000;")
        await self._exec("""
            CREATE TABLE IF NOT EXISTS conversions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                conv_type TEXT NOT NULL,
                filename TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                status TEXT NOT NULL,
                duration_ms INTEGER NOT NULL DEFAULT 0,
                error TEXT NOT NULL DEFAULT ''
            )
        """)
        await self._exec("""
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                media_message_id INTEGER NOT NULL DEFAULT 0,
                kind TEXT NOT NULL,
                file_id TEXT NOT NULL DEFAULT '',
                file_path TEXT NOT NULL DEFAULT '',
                work_dir TEXT NOT NULL DEFAULT '',
                extension TEXT NOT NULL DEFAULT '',
                duration REAL NOT NULL DEFAULT 0,
                width INTEGER NOT NULL DEFAULT 0,
                height INTEGER NOT NULL DEFAULT 0,
                settings_json TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            )
        """)
        await self._ensure_column("sessions", "settings_json", "settings_json TEXT NOT NULL DEFAULT ''")
        await self._exec("""
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                token TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                status TEXT NOT NULL,
                progress INTEGER NOT NULL DEFAULT 0,
                error TEXT NOT NULL DEFAULT '',
                message_id INTEGER NOT NULL DEFAULT 0,
                result_path TEXT NOT NULL DEFAULT '',
                media_message_id INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
        """)

    async def _exec(self, sql, params=None):
        async with self._conn.execute(sql, params or ()) as cur:
            await self._conn.commit()
            return cur

    async def _ensure_column(self, table, col, ddl):
        try:
            cols = [r["name"] for r in await self._fetchall(f"PRAGMA table_info({table})")]
        except Exception:
            return
        if col not in cols:
            await self._exec(f"ALTER TABLE {table} ADD COLUMN {ddl}")

    async def _fetchone(self, sql, params=None):
        async with self._conn.execute(sql, params or ()) as cur:
            return await cur.fetchone()

    async def _fetchall(self, sql, params=None):
        async with self._conn.execute(sql, params or ()) as cur:
            return await cur.fetchall()

    async def record_conversion(self, user_id, conv_type, filename, status, duration_ms=0, error=""):
        await self._exec(
            "INSERT INTO conversions (user_id, conv_type, filename, created_at, status, duration_ms, error) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, conv_type, filename[:200], iso_now(), status, int(duration_ms), error[:400]),
        )

    async def history(self, user_id, limit=10):
        rows = await self._fetchall(
            "SELECT conv_type, filename, created_at, status, duration_ms FROM conversions "
            "WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        )
        return [dict(r) for r in rows]

    async def clear_history(self, user_id):
        await self._exec("DELETE FROM conversions WHERE user_id = ?", (user_id,))

    async def create_session(self, token, user_id, chat_id, media_message_id, kind, file_id,
                             file_path, work_dir, extension, duration, width, height, ttl,
                             settings_json=""):
        await self._exec(
            "INSERT INTO sessions (token, user_id, chat_id, media_message_id, kind, file_id, file_path, "
            "work_dir, extension, duration, width, height, settings_json, created_at, expires_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (token, user_id, chat_id, media_message_id, kind, file_id, file_path, work_dir,
             extension, duration, width, height, settings_json, iso_now(), iso_now()),
        )
        return token

    async def get_session(self, token):
        row = await self._fetchone("SELECT * FROM sessions WHERE token = ?", (token,))
        return dict(row) if row else None

    async def update_session(self, token, **fields):
        if not fields:
            return
        cols = ", ".join(f"{k} = ?" for k in fields)
        params = list(fields.values())
        params.append(token)
        await self._exec(f"UPDATE sessions SET {cols} WHERE token = ?", params)

    async def sessions_for_user(self, user_id):
        rows = await self._fetchall("SELECT * FROM sessions WHERE user_id = ?", (user_id,))
        return [dict(r) for r in rows]

    async def delete_session(self, token):
        await self._exec("DELETE FROM sessions WHERE token = ?", (token,))

    async def list_expired_sessions(self, ttl):
        from datetime import datetime, timedelta, timezone
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=ttl)).isoformat()
        rows = await self._fetchall("SELECT * FROM sessions WHERE expires_at <= ?", (cutoff,))
        return [dict(r) for r in rows]

    async def purge_expired_sessions(self, ttl):
        rows = await self._fetchall("SELECT * FROM sessions")
        from datetime import datetime, timezone
        cutoff = _now_ts() - ttl
        for r in rows:
            try:
                created = datetime.fromisoformat(r["created_at"]).timestamp()
            except (TypeError, ValueError):
                created = None
            if created is None or created < cutoff:
                await self.delete_session(r["token"])

    async def create_job(self, job_id, token, user_id, chat_id, media_message_id):
        await self._exec(
            "INSERT INTO jobs (job_id, token, user_id, chat_id, status, created_at, media_message_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (job_id, token, user_id, chat_id, "queued", iso_now(), media_message_id),
        )

    async def update_job(self, job_id, **fields):
        cols = ", ".join(f"{k} = ?" for k in fields)
        params = list(fields.values())
        params.append(job_id)
        await self._exec(f"UPDATE jobs SET {cols} WHERE job_id = ?", params)

    async def get_job(self, job_id):
        row = await self._fetchone("SELECT * FROM jobs WHERE job_id = ?", (job_id,))
        return dict(row) if row else None

    async def active_job_for_token(self, token):
        row = await self._fetchone(
            "SELECT * FROM jobs WHERE token = ? AND status IN ('running', 'queued') ORDER BY created_at DESC LIMIT 1",
            (token,),
        )
        return dict(row) if row else None

    async def cleanup_jobs(self):
        await self._exec("DELETE FROM jobs WHERE status IN ('done', 'failed', 'cancelled')")


def _now_ts():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).timestamp()


_db = None


def db():
    return _db


def set_db(instance):
    global _db
    _db = instance