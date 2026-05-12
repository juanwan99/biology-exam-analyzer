"""report_data 数据聚合层测试"""
import pytest


def _make_question(qid, difficulty, bloom, total_score, knowledge_points=None,
                   competency=None, analysis=None):
    """构造完整题目 dict"""
    features = {"bloom": bloom, "reasoning_steps": 4, "knowledge_breadth": 2,
                "info_density": 2, "novelty": 2, "representation_complexity": 1}
    return {
        "id": qid,
        "total_score": total_score,
        "question_type": "single_choice",
        "difficulty": {
            "final_difficulty": difficulty,
            "difficulty_label": "中等",
            "cognitive_level": round(bloom / 6.0 * 10.0, 1),
            "confidence": 0.85,
            "features": features,
            "score_distribution_by_difficulty": {},
        },
        "analysis": {
            "knowledge_points": knowledge_points or ["光合作用"],
            "detailed_analysis": "解题步骤...",
            "common_mistakes": ["常见错误1"],
            "total_score": total_score,
        },
        "competency": competency or {
            "生命观念": {"涉及": True, "权重": 0.3, "具体维度": ["结构与功能观"], "分析说明": "..."},
            "科学思维": {"涉及": False, "权重": 0, "具体维度": [], "分析说明": ""},
            "科学探究": {"涉及": False, "权重": 0, "具体维度": [], "分析说明": ""},
            "社会责任": {"涉及": False, "权重": 0, "具体维度": [], "分析说明": ""},
            "primary_competency": "生命观念",
            "competency_level": "中",
        },
    }


from report_data import aggregate_report_data


class TestAggregateReportData:

    def test_total_score_from_analysis_fallback(self):
        """total_score 在 analysis 子字典中时也能正确取到"""
        # 模拟实际数据结构：total_score 在 analysis 中，不在顶层
        q = {
            "id": 1,
            "question_type": "single_choice",
            "analysis": {
                "total_score": 6,
                "knowledge_points": ["光合作用"],
                "detailed_analysis": "...",
                "common_mistakes": [],
            },
            "difficulty": {
                "final_difficulty": 5.0, "difficulty_label": "中等",
                "cognitive_level": 5.0, "confidence": 0.85,
                "features": {"bloom": 3, "reasoning_steps": 4, "knowledge_breadth": 2,
                             "info_density": 2, "novelty": 2, "representation_complexity": 1},
                "score_distribution_by_difficulty": {},
            },
            "competency": {"primary_competency": "生命观念", "competency_level": "中"},
        }
        statistics = {
            "avg_difficulty": 5.0, "avg_cognitive_level": 5.0,
            "difficulty_distribution": {}, "difficulty_distribution_by_score": {},
            "bloom_distribution": {}, "difficulty_curve": [],
            "top_knowledge_points": [], "knowledge_textbook_distribution": {},
            "competency_distribution": {},
        }
        result = aggregate_report_data([q], {}, statistics,
                                       {"name": "t", "total": 1, "mode": "fast"})
        assert result["exam_info"]["total_score"] == 6  # 不是 0
        assert result["questions"][0]["total_score"] == 6  # 不是 0

    def test_returns_all_top_level_keys(self):
        """返回值包含所有必需的顶层 key"""
        questions = [_make_question(1, 5.0, 3, 6)]
        statistics = {
            "avg_difficulty": 5.0, "avg_cognitive_level": 5.0,
            "difficulty_distribution": {"简单": 0, "中等": 1, "困难": 0},
            "difficulty_distribution_by_score": {},
            "bloom_distribution": {"识记": 0, "理解": 0, "应用": 1.0, "分析": 0, "评价": 0, "创造": 0},
            "difficulty_curve": [{"question_id": 1, "difficulty": 5.0, "total_score": 6}],
            "top_knowledge_points": [{"name": "光合作用", "weighted_score": 6.0}],
            "knowledge_textbook_distribution": {},
            "competency_distribution": {},
        }
        result = aggregate_report_data(
            questions=questions,
            competency_summary={},
            exam_statistics=statistics,
            exam_info={"name": "测试卷", "total": 1, "mode": "fast"},
        )
        assert set(result.keys()) == {
            "exam_info", "metrics", "difficulty_curve", "difficulty_gradient",
            "knowledge", "competency", "feature_profile", "questions",
        }

    def test_feature_profile_averages_6_dimensions(self):
        """feature_profile 聚合 6 维均值（排除 question_type_factor）"""
        questions = [
            _make_question(1, 5.0, 4, 6),
            _make_question(2, 3.0, 2, 4),
        ]
        # bloom: (4+2)/2=3, reasoning_steps: (4+4)/2=4, etc.
        statistics = {"avg_difficulty": 4.2, "avg_cognitive_level": 5.0,
                      "difficulty_distribution": {}, "difficulty_distribution_by_score": {},
                      "bloom_distribution": {}, "difficulty_curve": [],
                      "top_knowledge_points": [], "knowledge_textbook_distribution": {},
                      "competency_distribution": {}}
        result = aggregate_report_data(questions, {}, statistics,
                                       {"name": "t", "total": 2, "mode": "fast"})
        avg = result["feature_profile"]["avg_per_dimension"]
        assert avg["bloom"] == 3.0
        assert "question_type_factor" not in avg

    def test_difficulty_gradient_three_segments(self):
        """difficulty_gradient 计算前中后三段"""
        questions = [_make_question(i, float(i), 3, 2) for i in range(1, 10)]
        curve = [{"question_id": i, "difficulty": float(i), "total_score": 2} for i in range(1, 10)]
        statistics = {"avg_difficulty": 5.0, "avg_cognitive_level": 5.0,
                      "difficulty_distribution": {}, "difficulty_distribution_by_score": {},
                      "bloom_distribution": {}, "difficulty_curve": curve,
                      "top_knowledge_points": [], "knowledge_textbook_distribution": {},
                      "competency_distribution": {}}
        result = aggregate_report_data(questions, {}, statistics,
                                       {"name": "t", "total": 9, "mode": "fast"})
        grad = result["difficulty_gradient"]
        assert grad["front"] < grad["back"]  # 递增
        assert grad["gradient_type"] in ["前易后难（递增）", "前难后易（递减）", "难度均衡", "难度波动较大"]

    def test_question_details_extract_all_fields(self):
        """逐题详情提取全部字段"""
        questions = [_make_question(1, 5.0, 3, 6)]
        statistics = {"avg_difficulty": 5.0, "avg_cognitive_level": 5.0,
                      "difficulty_distribution": {}, "difficulty_distribution_by_score": {},
                      "bloom_distribution": {}, "difficulty_curve": [],
                      "top_knowledge_points": [], "knowledge_textbook_distribution": {},
                      "competency_distribution": {}}
        result = aggregate_report_data(questions, {}, statistics,
                                       {"name": "t", "total": 1, "mode": "fast"})
        q = result["questions"][0]
        assert q["id"] == 1
        assert q["bloom"] == 3
        assert q["bloom_reason"] is not None
        assert q["knowledge_points"] == ["光合作用"]
        assert q["detailed_analysis"] == "解题步骤..."
        assert q["primary_competency"] == "生命观念"
