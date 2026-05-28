import base64
import re

from services.agent_search_corpus import build_agent_search_documents


def test_build_agent_search_documents_returns_importable_documents():
    documents = build_agent_search_documents(max_documents=20)

    assert len(documents) >= 10
    for document in documents:
        assert re.fullmatch(r"[a-z0-9-]{1,63}", document["id"])
        assert document["structData"]["title"]
        assert document["structData"]["source"] == "biology_exam_review_corpus"
        assert document["content"]["mimeType"] == "text/plain"
        decoded = base64.b64decode(document["content"]["rawBytes"]).decode("utf-8")
        assert document["structData"]["title"] in decoded


def test_build_agent_search_documents_includes_quality_rubric_and_policy():
    documents = build_agent_search_documents(max_documents=100)
    titles = {document["structData"]["title"] for document in documents}
    categories = {document["structData"]["category"] for document in documents}

    assert "审题质量：语言、边界与风险" in titles
    assert "审题智能体策略：禁止静默失败" in titles
    assert {"quality", "rubric", "difficulty", "competency", "policy"} <= categories
