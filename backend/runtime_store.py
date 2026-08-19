# -*- coding: utf-8 -*-
"""SQLite-backed runtime state for tokens, split sessions, and analysis tasks."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from logger import get_logger

logger = get_logger()

TOKEN_TTL_SECONDS = int(os.getenv("TOKEN_TTL_SECONDS", "86400"))
SESSION_EXPIRE_MINUTES = int(os.getenv("SESSION_EXPIRE_MINUTES", "30"))
TASK_TTL_HOURS = int(os.getenv("TASK_TTL_HOURS", "2"))

_DEFAULT_PATH = Path(os.getenv("RUNTIME_DB_PATH", "/app/data/runtime.sqlite"))
_lock = threading.RLock()
_conn = None
_using_memory = False


def _now():
    return datetime.now()


def _iso(dt):
    return dt.isoformat()


def _parse(iso):
    return datetime.fromisoformat(iso)


def _schema(conn):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS tokens (
            token TEXT PRIMARY KEY,
            payload TEXT NOT NULL,
            expires_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            payload TEXT NOT NULL,
            expires_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS tasks (
            task_id TEXT PRIMARY KEY,
            payload TEXT NOT NULL,
            expires_at TEXT NOT NULL
        );
        """
    )


def _connect(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    _schema(conn)
    conn.commit()
    return conn


def init(path=None):
    global _conn, _using_memory
    if _conn is not None:
        return
    target = path or _DEFAULT_PATH
    try:
        _conn = _connect(target)
        _using_memory = False
        purge_expired()
        logger.info("[runtime_store] opened %s", target)
    except Exception as e:
        logger.error("[runtime_store] disk open failed (%s); using memory fallback", e)
        _conn = sqlite3.connect(":memory:", check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _schema(_conn)
        _using_memory = True


def _db():
    if _conn is None:
        init()
    return _conn


def purge_expired():
    now = _iso(_now())
    try:
        with _lock:
            db = _db()
            for table in ("tokens", "sessions", "tasks"):
                db.execute("DELETE FROM %s WHERE expires_at < ?" % table, (now,))
            db.commit()
    except Exception as e:
        logger.warning("[runtime_store] purge failed: %s", e)


def _get(table, key_col, key):
    try:
        with _lock:
            db = _db()
            row = db.execute(
                "SELECT payload, expires_at FROM %s WHERE %s = ?" % (table, key_col),
                (key,),
            ).fetchone()
            if not row:
                return None
            if _parse(row["expires_at"]) < _now():
                db.execute("DELETE FROM %s WHERE %s = ?" % (table, key_col), (key,))
                db.commit()
                return None
            return json.loads(row["payload"])
    except Exception as e:
        logger.warning("[runtime_store] get %s failed: %s", table, e)
        return None


def _put(table, key_col, key, payload, expires_at):
    try:
        with _lock:
            db = _db()
            db.execute(
                "INSERT OR REPLACE INTO %s (%s, payload, expires_at) VALUES (?, ?, ?)" % (table, key_col),
                (key, json.dumps(payload, ensure_ascii=False, default=str), _iso(expires_at)),
            )
            db.commit()
    except Exception as e:
        logger.warning("[runtime_store] put %s failed: %s", table, e)


def _delete(table, key_col, key):
    try:
        with _lock:
            db = _db()
            db.execute("DELETE FROM %s WHERE %s = ?" % (table, key_col), (key,))
            db.commit()
    except Exception as e:
        logger.warning("[runtime_store] delete %s failed: %s", table, e)


def get_token(token):
    return _get("tokens", "token", token)


def put_token(token, payload, ttl_seconds=TOKEN_TTL_SECONDS):
    _put("tokens", "token", token, payload, _now() + timedelta(seconds=ttl_seconds))


def delete_token(token):
    _delete("tokens", "token", token)


class TokenMap:
    def get(self, token, default=None):
        if not token:
            return default
        found = get_token(token)
        return found if found is not None else default

    def __contains__(self, token):
        return get_token(token) is not None

    def __getitem__(self, token):
        found = get_token(token)
        if found is None:
            raise KeyError(token)
        return found

    def __setitem__(self, token, payload):
        put_token(token, payload)

    def __delitem__(self, token):
        delete_token(token)


def save_session(session_id, data, minutes=SESSION_EXPIRE_MINUTES):
    _put("sessions", "session_id", session_id, {"data": data}, _now() + timedelta(minutes=minutes))


def get_session(session_id):
    row = _get("sessions", "session_id", session_id)
    if not row:
        return None
    return row.get("data")


def put_task(task_id, payload, hours=TASK_TTL_HOURS):
    _put("tasks", "task_id", task_id, payload, _now() + timedelta(hours=hours))


def get_task(task_id):
    return _get("tasks", "task_id", task_id)


def delete_task(task_id):
    _delete("tasks", "task_id", task_id)


def cleanup_tasks(max_age_hours=TASK_TTL_HOURS):
    try:
        with _lock:
            db = _db()
            cur = db.execute("DELETE FROM tasks WHERE expires_at < ?", (_iso(_now()),))
            db.commit()
            return cur.rowcount or 0
    except Exception as e:
        logger.warning("[runtime_store] cleanup_tasks failed: %s", e)
        return 0
