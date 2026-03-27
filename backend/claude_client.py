"""兼容垫片 — 保留旧 import 路径，实际逻辑已迁移到 llm_client.py。"""
from llm_client import (  # noqa: F401
    llm_call,
    send_message_gpt,
    send_message,
    send_message_with_image,
    AllProvidersFailed,
)
