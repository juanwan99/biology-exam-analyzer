"""Baseline tests for analysis pipeline — must pass before and after refactoring."""
import json
import pytest
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


class TestFixturesIntegrity:
    """Verify test fixtures are valid and complete."""

    def test_sample_questions_loadable(self):
        data = json.loads((FIXTURES / "sample_questions.json").read_text())
        assert len(data) == 3
        for q in data:
            assert "id" in q
            assert "content" in q
            assert "total_score" in q

    def test_fake_analysis_results_match_questions(self):
        questions = json.loads((FIXTURES / "sample_questions.json").read_text())
        results = json.loads((FIXTURES / "fake_analysis_results.json").read_text())
        for q in questions:
            assert str(q["id"]) in results

    def test_fake_difficulty_results_valid(self):
        results = json.loads((FIXTURES / "fake_difficulty_results.json").read_text())
        for qid, r in results.items():
            assert "final_difficulty" in r
            assert 0 <= r["final_difficulty"] <= 10
            assert "features" in r

    def test_fake_competency_results_valid(self):
        results = json.loads((FIXTURES / "fake_competency_results.json").read_text())
        for qid, r in results.items():
            assert "primary_competency" in r
            assert "competency_weights" in r
            weights = r["competency_weights"]
            assert abs(sum(weights.values()) - 1.0) < 0.01


class TestStatisticsFunction:
    """Test generate_exam_statistics with known data."""

    def test_statistics_with_fixture_data(self):
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from analysis_router import generate_exam_statistics

        questions = json.loads((FIXTURES / "sample_questions.json").read_text())
        analysis = json.loads((FIXTURES / "fake_analysis_results.json").read_text())
        difficulty = json.loads((FIXTURES / "fake_difficulty_results.json").read_text())
        competency = json.loads((FIXTURES / "fake_competency_results.json").read_text())

        for q in questions:
            q["analysis"] = analysis[str(q["id"])]
            q["difficulty"] = difficulty[str(q["id"])]
            q["competency"] = competency[str(q["id"])]

        competency_summary = {
            "primary_competency": "科学思维",
            "distribution": {"生命观念": 0.3, "科学思维": 0.4, "科学探究": 0.2, "社会责任": 0.1},
        }

        stats = generate_exam_statistics(questions, competency_summary)

        assert "error" not in stats
        assert "difficulty_distribution" in stats
        assert "bloom_distribution" in stats
        assert "avg_difficulty" in stats
        assert stats["difficulty_distribution"]["简单"] == 1
        assert stats["difficulty_distribution"]["中等"] == 2
        assert stats["avg_difficulty"] > 0


class TestFakeLlmClient:
    """Test the fake LLM client itself."""

    @pytest.mark.asyncio
    async def test_default_response(self):
        from tests.fakes.fake_llm_client import FakeLlmClient
        client = FakeLlmClient()
        result = await client.llm_call([{"role": "user", "content": "test question"}])
        data = json.loads(result)
        assert "knowledge_points" in data
        assert "answer" in data

    @pytest.mark.asyncio
    async def test_custom_response(self):
        from tests.fakes.fake_llm_client import FakeLlmClient
        client = FakeLlmClient()
        h = client.hash_content("specific question")
        client.add_response(h, json.dumps({"custom": True}))
        result = await client.llm_call([{"role": "user", "content": "specific question"}])
        assert json.loads(result)["custom"] is True

    @pytest.mark.asyncio
    async def test_call_logging(self):
        from tests.fakes.fake_llm_client import FakeLlmClient
        client = FakeLlmClient()
        await client.llm_call([{"role": "user", "content": "q1"}])
        await client.llm_call([{"role": "user", "content": "q2"}])
        assert len(client.call_log) == 2
