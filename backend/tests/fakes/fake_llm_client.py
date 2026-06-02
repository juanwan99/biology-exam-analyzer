"""Fake LLM client for deterministic pipeline testing."""
import json
import hashlib


class FakeLlmClient:
    """Returns canned responses keyed by content hash."""

    def __init__(self, responses: dict[str, str] | None = None):
        self.responses = responses or {}
        self.call_log: list[dict] = []

    def add_response(self, content_hash: str, response: str):
        self.responses[content_hash] = response

    @staticmethod
    def hash_content(text: str) -> str:
        return hashlib.md5(text[:200].encode()).hexdigest()[:12]

    async def llm_call(self, messages: list, **kwargs) -> str:
        user_msg = ""
        for m in messages:
            if m.get("role") == "user":
                content = m.get("content", "")
                if isinstance(content, str):
                    user_msg = content
                elif isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "text":
                            user_msg = item["text"]
                            break
                break

        h = self.hash_content(user_msg)
        self.call_log.append({"hash": h, "preview": user_msg[:100]})

        if h in self.responses:
            return self.responses[h]

        return json.dumps({
            "knowledge_points": ["光合作用"],
            "answer": "A",
            "total_score": 6,
            "analysis": "这是一道考查光合作用基本概念的选择题。",
            "common_mistakes": ["混淆光反应和暗反应"],
            "detailed_analysis": "步骤1：审题分析",
            "num_options": 4,
        })
