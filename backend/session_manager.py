# -*- coding: utf-8 -*-
"""
Session 管理模块

从 main.py 提取的 session 存储、过期清理、读写逻辑。
"""
from collections import OrderedDict
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import os

from logger import get_logger

logger = get_logger()

# ============ 配置 ============
SESSION_EXPIRE_MINUTES = int(os.getenv("SESSION_EXPIRE_MINUTES", "30"))

# Session 存储
SESSION_STORAGE = OrderedDict()
SESSION_EXPIRE_TIME = timedelta(minutes=SESSION_EXPIRE_MINUTES)


# ============ Session 操作 ============

def clean_expired_sessions():
    """清理过期的session"""
    current_time = datetime.now()
    expired_keys = [
        k for k, v in SESSION_STORAGE.items()
        if v["expire_time"] < current_time
    ]
    for key in expired_keys:
        del SESSION_STORAGE[key]
        logger.debug(f"清理过期session: {key}")


def save_session(session_id: str, data: Dict[str, Any]) -> None:
    """保存session数据"""
    clean_expired_sessions()
    SESSION_STORAGE[session_id] = {
        "data": data,
        "expire_time": datetime.now() + SESSION_EXPIRE_TIME
    }
    logger.info(f"保存session: {session_id}")


def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    """获取session数据"""
    clean_expired_sessions()
    session = SESSION_STORAGE.get(session_id)
    if session:
        return session["data"]
    return None
