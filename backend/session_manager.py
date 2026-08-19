# -*- coding: utf-8 -*-
"""Session store — SQLite via runtime_store, same public API."""
from typing import Dict, Any, Optional
import os

from logger import get_logger
import runtime_store

logger = get_logger()

SESSION_EXPIRE_MINUTES = int(os.getenv("SESSION_EXPIRE_MINUTES", "30"))


def clean_expired_sessions():
    runtime_store.purge_expired()


def save_session(session_id: str, data: Dict[str, Any]) -> None:
    runtime_store.save_session(session_id, data, minutes=SESSION_EXPIRE_MINUTES)
    logger.info("保存session: %s", session_id)


def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    return runtime_store.get_session(session_id)
