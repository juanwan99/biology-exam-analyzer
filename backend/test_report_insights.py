"""report_insights LLM 分析层测试（mock GPT 调用）"""
import pytest
import json
from unittest.mock import patch, AsyncMock

MOCK_OVERALL_RESPONSE = json.dumps({
    "overall_assessment": "本卷难度适中，知识覆盖较全面。",
    "recommendations": [
        {"category": "难度结构", "content": "建议增加过渡题", "priority": "high"},
        {"category": "知识覆盖", "content": "选修3覆盖不足", "priority": "medium"},
    ],
    "difficulty_analysis": "难度梯度呈递增趋势...",
    "knowledge_analysis": "知识点集中在必修1...",
    "competency_analysis": "科学探究素养覆盖不足...",
    "bloom_analysis": "高阶思维占比偏低...",
})

MOCK_COMMENTS_RESPONSE = json.dumps({
    "question_comments": {
        "1": "本题考查光合作用基本概念，属于识记层级。",
        "2": "本题需要分析系谱图推导基因型。",
    }
})


@pytest.fixture
def sample_report_data():
    return {
        "exam_info": {"name": "测试卷", "total_questions": 2, "total_score": 10, "mode": "fast"},
        "metrics": {"avg_difficulty": 5.0, "avg_cognitive_level": 5.0,
                    "difficulty_distribution": {"简单": 1, "中等": 1, "困难": 0},
                    "difficulty_distribution_by_score": {},
                    "bloom_distribution": {"应用": 0.6, "识记": 0.4}},
        "difficulty_curve": [],
        "difficulty_gradient": {"front": 3.0, "middle": 5.0, "back": 7.0, "gradient_type": "前易后难（递增）"},
        "knowledge": {"top_points": [{"name": "光合作用", "weighted_score": 6.0}],
                      "textbook_distribution": {}},
        "competency": {"distribution": {}, "primary_distribution": {}},
        "feature_profile": {"avg_per_dimension": {"bloom": 3.0, "reasoning_steps": 4.0,
                            "knowledge_breadth": 2.0, "info_density": 2.0,
                            "novelty": 2.0, "representation_complexity": 1.0},
                           "top_difficulty_factors": ["bloom", "reasoning_steps", "knowledge_breadth"]},
        "questions": [
            {"id": 1, "total_score": 6, "difficulty": 3.0, "bloom": 2,
             "knowledge_points": ["光合作用"], "primary_competency": "生命观念",
             "detailed_analysis": "步骤1...", "common_mistakes": ["错误1"]},
            {"id": 2, "total_score": 4, "difficulty": 7.0, "bloom": 4,
             "knowledge_points": ["遗传学"], "primary_competency": "科学思维",
             "detailed_analysis": "步骤1...", "common_mistakes": ["错误1"]},
        ],
    }


@pytest.mark.asyncio
class TestGenerateInsights:

    @patch("report_insights.send_message_gpt", new_callable=AsyncMock)
    async def test_brief_mode_one_call(self, mock_gpt, sample_report_data):
        """精简档只调用 1 次 GPT"""
        mock_gpt.return_value = MOCK_OVERALL_RESPONSE
        from report_insights import generate_insights
        result = await generate_insights(sample_report_data, mode="brief", grounding_enabled=False)
        assert mock_gpt.call_count == 2  # overall + teaching
        assert "overall_assessment" in result
        assert len(result["recommendations"]) >= 1
        assert "teaching_suggestions" in result

    @patch("report_insights.send_message_gpt", new_callable=AsyncMock)
    async def test_full_mode_one_call_with_comments_from_data(self, mock_gpt, sample_report_data):
        """完整档只调用 1 次 GPT（逐题点评从 report_data 复用）"""
        mock_gpt.return_value = MOCK_OVERALL_RESPONSE
        # 模拟 teacher_comment 已在 feature_extractor 中提取
        sample_report_data["questions"][0]["teacher_comment"] = "本题考查光合作用基本概念。"
        sample_report_data["questions"][1]["teacher_comment"] = "需要综合分析系谱图。"
        from report_insights import generate_insights
        result = await generate_insights(sample_report_data, mode="full", grounding_enabled=False)
        assert mock_gpt.call_count == 2  # overall + teaching
        assert "question_comments" in result
        assert "1" in result["question_comments"]
        assert "teaching_suggestions" in result



    @patch("report_insights.send_message_gpt", new_callable=AsyncMock)
    async def test_teaching_suggestions_structure(self, mock_gpt, sample_report_data):
        """教学建议返回包含三个子键"""
        mock_teaching = json.dumps({
            "error_categories": [
                {"category": "概念混淆", "description": "光合与呼吸混淆", "related_questions": [1], "frequency": "高"}
            ],
            "lecture_outline": [
                {"topic": "光合作用vs呼吸作用", "duration_minutes": 15, "key_points": ["区别要点"], "related_errors": ["概念混淆"]}
            ],
            "remedial_exercises": [
                {"knowledge_point": "光合作用", "exercise_type": "判断题", "difficulty": "中等"}
            ]
        })
        mock_gpt.side_effect = [MOCK_OVERALL_RESPONSE, mock_teaching]
        from report_insights import generate_insights
        result = await generate_insights(sample_report_data, mode="brief", grounding_enabled=False)
        ts = result["teaching_suggestions"]
        assert len(ts["error_categories"]) == 1
        assert ts["error_categories"][0]["category"] == "概念混淆"
        assert len(ts["lecture_outline"]) == 1
        assert len(ts["remedial_exercises"]) == 1

    @patch("report_insights.send_message_gpt", new_callable=AsyncMock)
    async def test_teaching_suggestions_failure_raises(self, mock_gpt, sample_report_data):
        """教学建议失败必须阻断，不能用空结构伪装成功。"""
        mock_gpt.side_effect = [
            MOCK_OVERALL_RESPONSE,
            RuntimeError("API timeout"),
            RuntimeError("compact timeout"),
            RuntimeError("ultra compact timeout"),
        ]
        from report_insights import generate_insights
        with pytest.raises(RuntimeError, match="LLM .*生成失败"):
            await generate_insights(sample_report_data, mode="brief", grounding_enabled=False)

    @patch("report_insights.send_message_gpt", new_callable=AsyncMock)
    async def test_teaching_suggestions_compact_retry_succeeds(self, mock_gpt, sample_report_data):
        """教学建议长输出失败时可用短格式重试，但仍必须来自 LLM JSON。"""
        compact_teaching = json.dumps({
            "error_categories": [
                {"category": "审题不清", "description": "忽略限定词", "related_questions": [2], "frequency": "中"}
            ],
            "lecture_outline": [
                {"topic": "限定词辨析", "duration_minutes": 10, "key_points": ["圈画关键词"], "related_errors": ["审题不清"]}
            ],
            "remedial_exercises": [
                {"knowledge_point": "激素调节", "exercise_type": "选择题", "difficulty": "中等"}
            ],
        })
        mock_gpt.side_effect = [
            MOCK_OVERALL_RESPONSE,
            RuntimeError("finish_reason=length"),
            compact_teaching,
        ]
        from report_insights import generate_insights

        result = await generate_insights(sample_report_data, mode="brief", grounding_enabled=False)

        assert mock_gpt.call_count == 3
        assert result["teaching_suggestions"]["error_categories"][0]["category"] == "审题不清"
        teaching_call = result["_llm_calls"][-1]
        assert teaching_call["metadata"]["retry_count"] == 1
        assert teaching_call["metadata"]["compact_retry"] is True
        assert teaching_call["metadata"]["retry_strategy"] == "compact"

    @patch("report_insights.send_message_gpt", new_callable=AsyncMock)
    async def test_teaching_suggestions_ultra_compact_retry_succeeds(self, mock_gpt, sample_report_data):
        """普通短格式仍超长时，继续用更硬的短 JSON 模板重试。"""
        ultra_teaching = json.dumps({
            "error_categories": [
                {"category": "推理错误", "description": "证据链不完整", "related_questions": [2], "frequency": "中"}
            ],
            "lecture_outline": [
                {"topic": "证据推理", "duration_minutes": 8, "key_points": ["先证后结"], "related_errors": ["推理错误"]},
                {"topic": "图表判断", "duration_minutes": 10, "key_points": ["读轴看量"], "related_errors": ["推理错误"]},
            ],
            "remedial_exercises": [
                {"knowledge_point": "遗传分析", "exercise_type": "选择题", "difficulty": "中等"},
                {"knowledge_point": "图表分析", "exercise_type": "非选择题", "difficulty": "中等"},
            ],
        })
        mock_gpt.side_effect = [
            MOCK_OVERALL_RESPONSE,
            RuntimeError("finish_reason=length"),
            RuntimeError("finish_reason=length"),
            ultra_teaching,
        ]
        from report_insights import generate_insights

        result = await generate_insights(sample_report_data, mode="brief", grounding_enabled=False)

        assert mock_gpt.call_count == 4
        assert result["teaching_suggestions"]["error_categories"][0]["category"] == "推理错误"
        teaching_call = result["_llm_calls"][-1]
        assert teaching_call["metadata"]["retry_count"] == 2
        assert teaching_call["metadata"]["compact_retry"] is True
        assert teaching_call["metadata"]["retry_strategy"] == "ultra_compact"

    @patch("report_insights.send_message_gpt", new_callable=AsyncMock)
    async def test_teaching_budget_adequate_and_non_shrinking(self, mock_gpt, sample_report_data):
        """RC6: deepseek-v4-pro 推理模型 reasoning 先吃预算，teaching 预算必须充足且重试不缩。
        防回归到 4096/1536/768 shrink 阶梯（对推理模型必然 finish_reason=length -> 报告崩）。"""
        valid_teaching = json.dumps({
            "error_categories": [
                {"category": "推理错误", "description": "因果倒置", "related_questions": [2], "frequency": "中"}
            ],
            "lecture_outline": [
                {"topic": "证据推理", "duration_minutes": 10, "key_points": ["先证后断"], "related_errors": ["推理错误"]}
            ],
            "remedial_exercises": [
                {"knowledge_point": "遗传规律", "exercise_type": "非选择题", "difficulty": "中等"}
            ],
        })
        mock_gpt.side_effect = [
            MOCK_OVERALL_RESPONSE,
            RuntimeError("openai_chat provider_incomplete_response: finish_reason=length"),
            RuntimeError("openai_chat provider_incomplete_response: finish_reason=length"),
            valid_teaching,
        ]
        from report_insights import generate_insights
        result = await generate_insights(sample_report_data, mode="brief", grounding_enabled=False)
        assert "teaching_suggestions" in result
        budgets = [
            c.kwargs["max_tokens"]
            for c in mock_gpt.call_args_list
            if c.kwargs.get("purpose") == "report_teaching_suggestions"
        ]
        assert budgets, "未捕获到 teaching 调用"
        assert budgets[0] >= 8192, f"primary 预算不足: {budgets[0]}"
        assert all(b >= 8192 for b in budgets), f"重试预算饥饿: {budgets}"
        assert budgets == sorted(budgets), f"重试预算应单调不降(不缩): {budgets}"

    @patch("report_insights.send_message_gpt", new_callable=AsyncMock)
    async def test_gpt_failure_raises(self, mock_gpt, sample_report_data):
        """GPT 失败直接抛异常，不降级"""
        mock_gpt.side_effect = RuntimeError("API 超时")
        from report_insights import generate_insights
        with pytest.raises(RuntimeError, match="LLM 分析生成失败"):
            await generate_insights(sample_report_data, mode="brief", grounding_enabled=False)

    @patch("report_insights.send_message_gpt", new_callable=AsyncMock)
    async def test_grounding_enabled_attaches_check_result(self, mock_gpt, sample_report_data):
        """开启 grounding 后，整卷综合分析需要留下证据校验结果。"""
        mock_gpt.return_value = MOCK_OVERALL_RESPONSE

        class FakeGateway:
            def __init__(self):
                self.calls = []

            async def check_grounding(self, **kwargs):
                self.calls.append(kwargs)
                return {
                    "status": "ok",
                    "support_score": 0.84,
                    "threshold": 0.6,
                    "claim_count": 3,
                    "cited_chunk_count": 2,
                    "metadata": {"provider": "evidence_service"},
                }

        gateway = FakeGateway()
        from report_insights import generate_insights

        result = await generate_insights(
            sample_report_data,
            mode="brief",
            evidence_gateway=gateway,
            grounding_enabled=True,
        )

        assert len(gateway.calls) >= 4
        assert "本卷难度适中" in gateway.calls[0]["answer"]
        assert gateway.calls[0]["facts"]
        grounded_sections = [check["section"] for check in result["_grounding_checks"]]
        assert "overall_assessment" in grounded_sections
        assert "difficulty_analysis" in grounded_sections
        assert "knowledge_analysis" in grounded_sections
        assert grounded_sections
        assert len(result["_grounding_checks"]) == len(gateway.calls)
        assert result["_grounding_checks"][0]["status"] == "ok"
        assert result["_grounding_checks"][0]["support_score"] == 0.84
        assert result["_llm_calls"][1]["purpose"] == "report_grounding_check"
        assert result["_llm_calls"][1]["provider"] == "evidence_service"
        assert result["_llm_calls"][1]["model"] == "check_grounding"
        assert result["_llm_calls"][1]["metadata"]["section_count"] == len(gateway.calls)

    async def test_grounding_facts_are_section_cards_and_traceable(self, sample_report_data):
        from report_insights import _build_grounding_facts

        facts = _build_grounding_facts(sample_report_data)
        sources = {
            (fact.get("attributes") or {}).get("source")
            for fact in facts
        }

        assert 5 <= len(facts) <= 20
        assert "report.evidence_card.overall" in sources
        assert "report.evidence_card.difficulty" in sources
        assert "report.evidence_card.difficulty_distribution_detail" in sources
        assert "report.evidence_card.bloom" in sources
        assert "report.evidence_card.knowledge" in sources
        assert "report.evidence_card.competency" in sources
        assert "report.evidence_card.feature_profile" in sources
        assert "report.evidence_card.summary" in sources
        assert "report.evidence_card.recommendation_basis" in sources
        assert "report.evidence_card.recommendation_policy" in sources
        assert all(len(str(fact.get("factText") or "")) <= 1200 for fact in facts)
        assert "report.metrics" not in sources
        difficulty_card = next(
            fact for fact in facts
            if (fact.get("attributes") or {}).get("source") == "report.evidence_card.difficulty"
        )
        assert "avg_difficulty" in difficulty_card["factText"]
        assert "difficulty_gradient" in difficulty_card["factText"]
        difficulty_detail_card = next(
            fact for fact in facts
            if (fact.get("attributes") or {}).get("source")
            == "report.evidence_card.difficulty_distribution_detail"
        )
        assert "简单题为1题。" in difficulty_detail_card["factText"]
        assert "中等题为1题。" in difficulty_detail_card["factText"]
        assert "困难题为0题。" in difficulty_detail_card["factText"]
        summary_card = next(
            fact for fact in facts
            if (fact.get("attributes") or {}).get("source") == "report.evidence_card.summary"
        )
        assert "top_difficulty_factors" in summary_card["factText"]
        recommendation_card = next(
            fact for fact in facts
            if (fact.get("attributes") or {}).get("source") == "report.evidence_card.recommendation_basis"
        )
        assert "recommendation_basis" in recommendation_card["factText"]
        policy_card = next(
            fact for fact in facts
            if (fact.get("attributes") or {}).get("source") == "report.evidence_card.recommendation_policy"
        )
        assert "recommendation_policy" in policy_card["factText"]
        assert "hard_score_share" in policy_card["factText"]
        feature_card = next(
            fact for fact in facts
            if (fact.get("attributes") or {}).get("source") == "report.evidence_card.feature_profile"
        )
        assert "top_difficulty_factor_aliases" in feature_card["factText"]
        assert "对难度贡献最大的维度包含" in feature_card["factText"]

    async def test_grounding_facts_expand_all_primary_competency_counts(self, sample_report_data):
        from report_insights import _build_grounding_facts

        sample_report_data["competency"]["primary_distribution"] = {
            "生命观念": 11,
            "科学思维": 10,
            "科学探究": 0,
            "社会责任": 0,
        }

        facts = _build_grounding_facts(sample_report_data)
        competency_card = next(
            fact for fact in facts
            if (fact.get("attributes") or {}).get("source") == "report.evidence_card.competency"
        )

        assert "主要素养分布中科学思维为10题" in competency_card["factText"]
        assert "主要素养分布中生命观念为11题" in competency_card["factText"]

    async def test_grounding_sections_split_long_analysis_into_short_claims(self):
        from report_insights import _build_grounding_sections

        sections = _build_grounding_sections({
            "bloom_analysis": "平均认知层级为6.47。高阶思维占比为58.8%。对难度贡献最大的维度包含认知层级。",
        })

        names = [section["section"] for section in sections]
        answers = [section["answer"] for section in sections]
        assert names == ["bloom_analysis#1", "bloom_analysis#2", "bloom_analysis#3"]
        assert answers[0] == "平均认知层级为6.47。"

    async def test_grounding_sections_check_recommendation_basis_not_directive(self):
        from report_insights import _build_grounding_sections

        sections = _build_grounding_sections({
            "difficulty_analysis": "简单题为0题。建议增加简单题。",
            "recommendations": [
                {
                    "category": "难度调整",
                    "content": "困难题分值占比为61.2%。建议降低困难题比例或增加低门槛题。",
                },
            ],
        })

        answers = [section["answer"] for section in sections]
        recommendation_section = next(
            section for section in sections
            if section["section"] == "recommendations"
        )

        assert "建议增加简单题。" not in answers
        assert recommendation_section["answer"] == "困难题分值占比为61.2%。"
        assert recommendation_section["kind"] == "policy_basis"
        assert "建议降低困难题比例" in recommendation_section["policy_text"]

    async def test_grounding_sections_skip_pure_policy_and_low_signal_claims(self):
        from report_insights import _build_grounding_sections

        sections = _build_grounding_sections({
            "difficulty_analysis": "\u5efa\u8bae\u5927\u5e45\u8c03\u6574\u56f0\u96be\u9898\u6bd4\u4f8b\uff0c\u589e\u52a0\u7b80\u5355\u9898\u3002",
            "knowledge_analysis": "\u8584\u5f31\u73af\u8282\u5728\u9009\u62e9\u6027\u5fc5\u4fee3\uff0c\u5982\u57fa\u56e0\u5de5\u7a0b\u3001\u7ec6\u80de\u5de5\u7a0b\u7b49\u6a21\u5757\u8003\u67e5\u4e0d\u8db3\u3002",
            "bloom_analysis": "\u9ad8\u9636\u601d\u7ef4\uff08\u5206\u6790\u3001\u8bc4\u4ef7\u3001\u521b\u9020\uff09\u5408\u8ba1\u536054.0%\uff0c\u6574\u4f53\u601d\u7ef4\u5c42\u7ea7\u8f83\u9ad8\uff0c\u4f46\u57fa\u7840\u6027\u8bc6\u8bb0\u8003\u67e5\u4e0d\u8db3\uff0c\u53ef\u80fd\u5f71\u54cd\u4f4e\u5c42\u6b21\u8ba4\u77e5\u7684\u8986\u76d6\u9762\u3002",
        })

        answers = [section["answer"] for section in sections]
        assert "\u5efa\u8bae\u5927\u5e45\u8c03\u6574\u56f0\u96be\u9898\u6bd4\u4f8b\u3002" not in answers
        assert not any("\u8584\u5f31\u73af\u8282" in answer for answer in answers)
        assert any("54.0%" in answer for answer in answers)
        assert not any("\u53ef\u80fd\u5f71\u54cd" in answer for answer in answers)

    async def test_grounding_sections_rewrite_pronoun_score_claims(self):
        from report_insights import _build_grounding_sections

        text = (
            "\u6743\u91cd\u6700\u9ad8\u7684\u77e5\u8bc6\u70b9\u4e3a\u57fa\u56e0\u7684\u5206\u79bb\u5b9a\u5f8b\u3002"
            "\u5176\u52a0\u6743\u5206\u503c\u4e3a4.5\u3002"
            "\u5176\u6b21\u4e3a\u751f\u6001\u5de5\u7a0b\u7684\u57fa\u672c\u539f\u7406\u3002"
            "\u5176\u52a0\u6743\u5206\u503c\u4e3a4.1\u3002"
        )

        sections = _build_grounding_sections({"knowledge_analysis": text})
        answers = [section["answer"] for section in sections]

        assert "\u6700\u9ad8\u6743\u91cd\u77e5\u8bc6\u70b9\u4e3a\u57fa\u56e0\u7684\u5206\u79bb\u5b9a\u5f8b\u3002" in answers
        assert "\u7b2c\u4e8c\u9ad8\u6743\u91cd\u77e5\u8bc6\u70b9\u4e3a\u751f\u6001\u5de5\u7a0b\u7684\u57fa\u672c\u539f\u7406\u3002" in answers
        assert "\u57fa\u56e0\u7684\u5206\u79bb\u5b9a\u5f8b\u52a0\u6743\u5206\u503c\u4e3a4.5\u3002" in answers
        assert "\u751f\u6001\u5de5\u7a0b\u7684\u57fa\u672c\u539f\u7406\u52a0\u6743\u5206\u503c\u4e3a4.1\u3002" in answers
        assert "\u5176\u52a0\u6743\u5206\u503c\u4e3a4.1\u3002" not in answers

    async def test_grounding_facts_include_ranked_knowledge_detail(self, sample_report_data):
        from report_insights import _build_grounding_facts

        sample_report_data["knowledge"]["top_points"] = [
            {"name": "\u57fa\u56e0\u7684\u5206\u79bb\u5b9a\u5f8b", "weighted_score": 4.5, "question_count": 3},
            {"name": "\u751f\u6001\u5de5\u7a0b\u7684\u57fa\u672c\u539f\u7406", "weighted_score": 4.1, "question_count": 2},
        ]

        facts = _build_grounding_facts(sample_report_data)
        detail = next(
            fact for fact in facts
            if (fact.get("attributes") or {}).get("source") == "report.evidence_card.knowledge_detail"
        )

        assert "\u7b2c\u4e8c\u9ad8\u6743\u91cd\u77e5\u8bc6\u70b9\u4e3a\u751f\u6001\u5de5\u7a0b\u7684\u57fa\u672c\u539f\u7406" in detail["factText"]
        assert "\u751f\u6001\u5de5\u7a0b\u7684\u57fa\u672c\u539f\u7406\u52a0\u6743\u5206\u503c\u4e3a4.1" in detail["factText"]

    async def test_overall_prompt_requires_grounded_short_claims(self, sample_report_data):
        from report_insights import _build_overall_prompt

        prompt = _build_overall_prompt(sample_report_data)

        assert "Grounding requirements" in prompt
        assert "Grounding Evidence Cards" in prompt
        assert "每句只包含一个主要事实" in prompt
        assert "优先使用 Grounding Evidence Cards" in prompt
        assert "不要写“信度”" in prompt

    async def test_grounding_answer_separates_sections_with_blank_lines(self):
        from report_insights import _build_grounding_answer

        answer = _build_grounding_answer({
            "overall_assessment": "总评。",
            "difficulty_analysis": "难度。",
            "knowledge_analysis": "知识。",
            "competency_analysis": "素养。",
            "bloom_analysis": "认知。",
            "recommendations": [
                {"content": "建议一。"},
            ],
        })

        assert "知识。\n\n素养。" in answer
        assert "认知。\n\n建议一。" in answer

    async def test_grounding_facts_include_exact_zero_primary_summary(self, sample_report_data):
        from report_insights import _build_grounding_facts

        sample_report_data["competency"]["primary_distribution"] = {
            "生命观念": 1,
            "科学思维": 1,
            "科学探究": 0,
            "社会责任": 0,
        }

        facts = _build_grounding_facts(sample_report_data)
        joined = "\n".join(fact["factText"] for fact in facts)

        assert "主要素养为0题的维度为科学探究、社会责任" in joined

    @patch("report_insights.send_message_gpt", new_callable=AsyncMock)
    async def test_grounding_low_support_marks_report_needs_review(self, mock_gpt, sample_report_data):
        """低 supportScore 不伪装成功，应标记报告需复核。"""
        mock_gpt.return_value = MOCK_OVERALL_RESPONSE

        class FakeGateway:
            async def check_grounding(self, **kwargs):
                return {
                    "status": "needs_review",
                    "support_score": 0.42,
                    "threshold": 0.6,
                    "claim_count": 2,
                    "cited_chunk_count": 0,
                    "metadata": {"provider": "evidence_service"},
                }

        from report_insights import generate_insights

        result = await generate_insights(
            sample_report_data,
            mode="brief",
            evidence_gateway=FakeGateway(),
            grounding_enabled=True,
        )

        assert result["_grounding_status"] == "needs_review"
        assert result["_grounding_checks"][0]["support_score"] == 0.42

    @patch("report_insights.send_message_gpt", new_callable=AsyncMock)
    async def test_grounding_failure_raises_report_generation_error(self, mock_gpt, sample_report_data):
        """grounding 开启后失败必须中断报告生成，不能静默吞掉。"""
        mock_gpt.return_value = MOCK_OVERALL_RESPONSE

        class FailingGateway:
            async def check_grounding(self, **kwargs):
                raise RuntimeError("grounding permission denied")

        from report_insights import generate_insights

        with pytest.raises(RuntimeError, match="grounding permission denied"):
            await generate_insights(
                sample_report_data,
                mode="brief",
                evidence_gateway=FailingGateway(),
                grounding_enabled=True,
            )

    @patch("report_insights.send_message_gpt", new_callable=AsyncMock)
    async def test_report_llm_calls_record_actual_provider_model(self, mock_gpt, sample_report_data, monkeypatch):
        mock_gpt.return_value = MOCK_OVERALL_RESPONSE
        import report_insights

        monkeypatch.setattr(
            report_insights,
            "get_last_call_metadata",
            lambda: {
                "provider": "deepseek",
                "model": "deepseek-v4-pro",
                "fallback_count": 0,
                "provider_errors": [],
            },
            raising=False,
        )

        result = await report_insights.generate_insights(
            sample_report_data,
            mode="brief",
            grounding_enabled=False,
        )

        calls = result["_llm_calls"]
        assert calls[0]["purpose"] == "report_insights"
        assert calls[0]["provider"] == "deepseek"
        assert calls[0]["model"] == "deepseek-v4-pro"

    @patch("report_insights.send_message_gpt", new_callable=AsyncMock)
    async def test_report_llm_uses_deterministic_temperature(self, mock_gpt, sample_report_data):
        mock_gpt.return_value = MOCK_OVERALL_RESPONSE

        from report_insights import generate_insights

        await generate_insights(sample_report_data, mode="brief", grounding_enabled=False)

        temperatures = [
            call.kwargs.get("temperature")
            for call in mock_gpt.call_args_list
        ]
        assert temperatures
        assert all(value == 0.0 for value in temperatures)

    @patch("report_insights.send_message_gpt", new_callable=AsyncMock)
    async def test_report_overall_call_uses_large_enough_token_budget(self, mock_gpt, sample_report_data):
        mock_gpt.return_value = MOCK_OVERALL_RESPONSE

        from report_insights import generate_insights

        await generate_insights(sample_report_data, mode="brief", grounding_enabled=False)

        assert mock_gpt.call_args_list[0].kwargs["purpose"] == "report_insights"
        assert mock_gpt.call_args_list[0].kwargs["max_tokens"] >= 4096

    async def test_formal_grounded_insights_rewrite_unverified_llm_claims(self, sample_report_data):
        from report_insights import _stabilize_grounded_insights

        sample_report_data["metadata_quality"] = {"llm_call_counts": {"question_analysis": 2}}
        draft = {
            "overall_assessment": "UNSUPPORTED claim about unmeasured discrimination.",
            "recommendations": [],
            "difficulty_analysis": "",
            "knowledge_analysis": "",
            "competency_analysis": "",
            "bloom_analysis": "",
        }

        result = _stabilize_grounded_insights(draft, sample_report_data)

        assert result["_stabilized_for_grounding"] is True
        assert "UNSUPPORTED" not in result["overall_assessment"]
        assert "平均难度为5" in result["overall_assessment"]
        assert result["recommendations"]
