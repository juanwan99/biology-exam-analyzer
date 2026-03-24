"""结构化日志模块 — JSONL + Console 双输出。

对齐全局 logging-rules.md 标准。
B0 重写：RotatingFileHandler + ContextVar request_id + 环境变量级别控制。
"""
import logging
import json
import os
from datetime import datetime, timezone, timedelta
from contextvars import ContextVar
from logging.handlers import RotatingFileHandler
from pathlib import Path

# request_id 上下文变量（middleware.py 设置，各模块日志自动携带）
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

# 日志目录
LOG_DIR = Path(os.environ.get("LOG_DIR", os.path.join(os.path.dirname(__file__), "logs")))
LOG_DIR.mkdir(parents=True, exist_ok=True)

# UTC+8
_TZ = timezone(timedelta(hours=8))


class JSONLFormatter(logging.Formatter):
    """JSONL 格式化器 — 文件持久化用。"""

    def format(self, record):
        entry = {
            "ts": datetime.fromtimestamp(record.created, tz=_TZ).isoformat(),
            "level": record.levelname,
            "module": record.name,
            "msg": record.getMessage(),
            "req_id": request_id_var.get(),
        }
        if record.exc_info and record.exc_info[1]:
            entry["error"] = str(record.exc_info[1])
        if hasattr(record, "duration_ms"):
            entry["duration_ms"] = record.duration_ms
        return json.dumps(entry, ensure_ascii=False)


class ConsoleFormatter(logging.Formatter):
    """Console 人类可读格式化器。"""

    def format(self, record):
        ts = datetime.fromtimestamp(record.created, tz=_TZ).strftime("%H:%M:%S")
        req = request_id_var.get()
        prefix = f"[{ts}] [{record.levelname}] [{req}]" if req != "-" else f"[{ts}] [{record.levelname}]"
        return f"{prefix} {record.getMessage()}"


def _setup_logger():
    """初始化根 logger。"""
    logger = logging.getLogger("biology_analyzer")

    # 从环境变量读取级别（修复 G6：之前硬编码 DEBUG）
    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logger.setLevel(level)

    # 避免重复添加 handler
    if logger.handlers:
        return logger

    # File handler: JSONL + 轮转 (10MB × 5)
    file_handler = RotatingFileHandler(
        LOG_DIR / "app.jsonl",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)  # 文件记录所有级别
    file_handler.setFormatter(JSONLFormatter())
    logger.addHandler(file_handler)

    # Console handler: 人类可读
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(ConsoleFormatter())
    logger.addHandler(console_handler)

    return logger


# 模块级单例
_logger = _setup_logger()


def get_logger():
    return _logger
