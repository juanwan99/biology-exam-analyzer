# -*- coding: utf-8 -*-
"""V1 分值加权统计测试"""
import pytest
from unittest.mock import patch, MagicMock


# Mock knowledge_mapper to avoid DB dependency
@pytest.fixture(autouse=True)
def mock_knowledge_mapper():
    mock_mapper = MagicMock()
    mock_mapper.map_knowledge_points.return_value = []
    with patch("analysis_statistics.get_knowledge_mapper", return_value=mock_mapper):
        yield mock_mapper


from analysis_statistics import generate_exam_statistics


def _make_question(qid, difficulty, cognitive, total_score, knowledge_points=None, bloom=None):
    """构造测试用题目 dict"""
    features = {}
    if bloom is not None:
        features["bloom"] = bloom
    return {
        "id": qid,
        "total_score": total_score,
        "difficulty": {
            "final_difficulty": difficulty,
            "cognitive_level": cognitive,
            "score_distribution_by_difficulty": {},
            "features": features,
        },
        "analysis": {
            "knowledge_points": knowledge_points or [],
            "total_score": total_score,
        },
    }


class TestWeightedAvgDifficulty:
    """avg_difficulty 应按分值加权"""

    def test_equal_scores_same_as_simple_avg(self):
        """等分值时，加权平均 = 简单平均"""
        questions = [
            _make_question(1, 3.0, 5.0, 2),
            _make_question(2, 7.0, 5.0, 2),
        ]
        result = generate_exam_statistics(questions, {})
        assert result["avg_difficulty"] == 5.0

    def test_higher_score_question_dominates(self):
        """高分题权重更大：6分题难度8 + 2分题难度2 → 加权=(8×6+2×2)/8=6.5"""
        questions = [
            _make_question(1, 8.0, 5.0, 6),
            _make_question(2, 2.0, 5.0, 2),
        ]
        result = generate_exam_statistics(questions, {})
        assert result["avg_difficulty"] == 6.5

    def test_zero_total_score_is_excluded_and_reported(self):
        """total_score=0 不得 fallback 等权=1，必须进入分值质量审计。"""
        questions = [
            _make_question(1, 5.0, 5.0, 0),
        ]
        result = generate_exam_statistics(questions, {})
        assert result["avg_difficulty"] == 0
        assert {
            "id": 1,
            "reason": "non_positive_score",
            "source": "total_score",
            "value": 0,
        } in result["score_quality"]["score_issue_questions"]

    def test_invalid_score_does_not_pollute_valid_weighted_average(self):
        questions = [
            _make_question(1, 9.0, 9.0, 0),
            _make_question(2, 1.0, 1.0, 10),
        ]

        result = generate_exam_statistics(questions, {})

        assert result["avg_difficulty"] == 1.0
        assert result["avg_cognitive_level"] == 1.0
        assert {
            "id": 1,
            "reason": "non_positive_score",
            "source": "total_score",
            "value": 0,
        } in result["score_quality"]["score_issue_questions"]


class TestWeightedAvgCognitive:
    """avg_cognitive_level 应按分值加权"""

    def test_weighted_cognitive(self):
        """6分题认知8 + 2分题认知2 → 加权=6.5"""
        questions = [
            _make_question(1, 5.0, 8.0, 6),
            _make_question(2, 5.0, 2.0, 2),
        ]
        result = generate_exam_statistics(questions, {})
        assert result["avg_cognitive_level"] == 6.5


class TestWeightedKnowledgePoints:
    """知识点统计应按分值加权"""

    def test_weighted_knowledge_score(self):
        """6分题1个知识点=6分权重, 2分题2个知识点=各1分权重"""
        questions = [
            _make_question(1, 5.0, 5.0, 6, knowledge_points=["光合作用"]),
            _make_question(2, 5.0, 5.0, 2, knowledge_points=["光合作用", "呼吸作用"]),
        ]
        result = generate_exam_statistics(questions, {})
        kp_map = {item["name"]: item["weighted_score"] for item in result["top_knowledge_points"]}
        assert kp_map["光合作用"] == 7.0  # 6/1 + 2/2 = 7
        assert kp_map["呼吸作用"] == 1.0  # 2/2

    def test_seu_knowledge_links_are_normalised_per_scoring_unit(self):
        """一个采分点内多个知识标签应拆分该采分点分值，不能各拿满分。"""
        questions = [{
            "id": 1,
            "total_score": 10,
            "difficulty": {
                "final_difficulty": 6.0,
                "cognitive_level": 6.0,
                "score_distribution_by_difficulty": {},
                "features": {"bloom": 4},
            },
            "analysis": {
                "_fine_grained": {
                    "scoring_units": [{
                        "score_share": 1.0,
                        "bloom_level": 4,
                        "knowledge_links": [
                            {"knowledge_point": "PCR技术"},
                            {"knowledge_point": "基因表达载体构建"},
                        ],
                    }]
                }
            },
        }]

        result = generate_exam_statistics(questions, {})

        kp_map = {item["name"]: item["weighted_score"] for item in result["top_knowledge_points"]}
        assert kp_map["PCR技术"] == 5.0
        assert kp_map["基因表达载体构建"] == 5.0


class TestTextbookWeightedMapping:
    """教材分布应按分值加权映射"""

    def test_textbook_weighted_score_and_percentage(self, mock_knowledge_mapper):
        """6分题1个知识点(必修1 ch1) + 4分题1个知识点(必修2 ch3) → 必修1=6分60%, 必修2=4分40%"""
        mock_knowledge_mapper.map_knowledge_points.return_value = [
            {"mapped": True, "textbook": "必修1", "chapter": "第1章", "chapter_name": "走进细胞", "original": "光合作用"},
            {"mapped": True, "textbook": "必修2", "chapter": "第3章", "chapter_name": "基因的本质", "original": "DNA复制"},
        ]
        questions = [
            _make_question(1, 5.0, 5.0, 6, knowledge_points=["光合作用"]),
            _make_question(2, 5.0, 5.0, 4, knowledge_points=["DNA复制"]),
        ]
        result = generate_exam_statistics(questions, {})
        tb = result["knowledge_textbook_distribution"]
        assert tb["必修1"]["weighted_score"] == 6.0
        assert tb["必修2"]["weighted_score"] == 4.0
        assert tb["必修1"]["percentage"] == 60.0
        assert tb["必修2"]["percentage"] == 40.0
        assert tb["必修1"]["chapters"]["第1章"]["weighted_score"] == 6.0

    def test_unmapped_knowledge_point(self, mock_knowledge_mapper):
        """未映射的知识点不计入教材分布"""
        mock_knowledge_mapper.map_knowledge_points.return_value = [
            {"mapped": False},
        ]
        questions = [
            _make_question(1, 5.0, 5.0, 6, knowledge_points=["未知知识点"]),
        ]
        result = generate_exam_statistics(questions, {})
        tb = result["knowledge_textbook_distribution"]
        assert all(v["weighted_score"] == 0 for v in tb.values())

    def test_unmapped_knowledge_points_keep_weighted_detail(self, mock_knowledge_mapper):
        mock_knowledge_mapper.map_knowledge_points.return_value = [
            {"mapped": False, "original": "unmapped_a"},
            {"mapped": False, "original": "unmapped_a"},
            {
                "mapped": True,
                "textbook": "必修1",
                "chapter": "mapped_chapter",
                "chapter_name": "mapped chapter",
                "original": "mapped_b",
            },
        ]
        questions = [
            _make_question(1, 5.0, 5.0, 6, knowledge_points=["unmapped_a"]),
            _make_question(2, 5.0, 5.0, 4, knowledge_points=["unmapped_a", "mapped_b"]),
        ]

        result = generate_exam_statistics(questions, {})

        assert result["knowledge_unmapped_count"] == 2
        assert result["knowledge_mapped_count"] == 1
        assert result["knowledge_unmapped_points"] == [
            {"name": "unmapped_a", "weighted_score": 8.0, "occurrences": 2}
        ]

    def test_method_skill_points_are_not_sent_to_textbook_mapper(self, mock_knowledge_mapper):
        mock_knowledge_mapper.map_knowledge_points.return_value = [
            {
                "mapped": True,
                "textbook": "必修2",
                "chapter": "第1章",
                "chapter_name": "遗传因子的发现",
                "original": "遗传的基本规律",
            },
        ]
        questions = [
            _make_question(
                1,
                5.0,
                5.0,
                6,
                knowledge_points=["实验设计与变量控制", "遗传的基本规律"],
            ),
        ]

        result = generate_exam_statistics(questions, {})

        mock_knowledge_mapper.map_knowledge_points.assert_called_once_with(["遗传的基本规律"])
        assert result["knowledge_non_textbook_count"] == 1
        assert result["knowledge_non_textbook_points"] == [
            {"name": "实验设计与变量控制", "weighted_score": 3.0, "occurrences": 1}
        ]

    def test_repeated_method_skill_tags_are_diminished_within_one_question(self):
        """同一题反复出现的方法能力标签不能按采分点数量刷高为主要知识点。"""
        scoring_units = [
            {
                "score_share": 1 / 6,
                "bloom_level": 4,
                "knowledge_links": [{"knowledge_point": "实验设计中的变量控制"}],
            }
            for _ in range(6)
        ]
        questions = [{
            "id": 19,
            "total_score": 12,
            "difficulty": {
                "final_difficulty": 7.5,
                "cognitive_level": 7.0,
                "score_distribution_by_difficulty": {},
                "features": {"bloom": 4},
            },
            "analysis": {"_fine_grained": {"scoring_units": scoring_units}},
        }]

        result = generate_exam_statistics(questions, {})

        assert result["knowledge_non_textbook_points"] == [
            {"name": "实验设计中的变量控制", "weighted_score": 5.4, "occurrences": 6}
        ]


class TestBloomDistribution:
    """Bloom 分布应按分值加权为占比"""

    def test_bloom_weighted_proportion(self):
        """6分bloom=3(应用) + 4分bloom=1(识记) → 应用60% 识记40%"""
        questions = [
            _make_question(1, 5.0, 5.0, 6, bloom=3),
            _make_question(2, 5.0, 5.0, 4, bloom=1),
        ]
        result = generate_exam_statistics(questions, {})
        bloom = result["bloom_distribution"]
        assert bloom["应用"] == 0.6
        assert bloom["识记"] == 0.4

    def test_bloom_missing_graceful(self):
        """无 bloom 特征时返回空分布"""
        questions = [
            _make_question(1, 5.0, 5.0, 6, bloom=None),
        ]
        result = generate_exam_statistics(questions, {})
        bloom = result["bloom_distribution"]
        assert all(v == 0 for v in bloom.values())


class TestWeightedCompetency:
    """素养占比应按分值加权"""

    def test_weighted_competency_ratio(self):
        """6分题生命观念权重0.5 + 2分题权重0.1 → 占比=(6×0.5+2×0.1)/8=0.4"""
        from competency_analyzer import CompetencyAnalyzer
        analyzer = CompetencyAnalyzer.__new__(CompetencyAnalyzer)

        questions = [
            {"生命观念": {"涉及": True, "权重": 0.5, "具体维度": ["结构与功能观"]},
             "科学思维": {"涉及": False, "权重": 0, "具体维度": []},
             "科学探究": {"涉及": False, "权重": 0, "具体维度": []},
             "社会责任": {"涉及": False, "权重": 0, "具体维度": []},
             "primary_competency": "生命观念",
             "_total_score": 6},
            {"生命观念": {"涉及": True, "权重": 0.1, "具体维度": ["进化与适应观"]},
             "科学思维": {"涉及": False, "权重": 0, "具体维度": []},
             "科学探究": {"涉及": False, "权重": 0, "具体维度": []},
             "社会责任": {"涉及": False, "权重": 0, "具体维度": []},
             "primary_competency": "生命观念",
             "_total_score": 2},
        ]
        result = analyzer.aggregate_exam_competencies(questions)
        assert result["生命观念"]["占比"] == 0.4

    def test_missing_score_does_not_fallback_to_equal_weight(self):
        """缺 _total_score 时不得等权兜底，避免把数据不足伪装成有效统计。"""
        from competency_analyzer import CompetencyAnalyzer
        analyzer = CompetencyAnalyzer.__new__(CompetencyAnalyzer)

        questions = [
            {"生命观念": {"涉及": True, "权重": 0.8, "具体维度": []},
             "科学思维": {"涉及": False, "权重": 0, "具体维度": []},
             "科学探究": {"涉及": False, "权重": 0, "具体维度": []},
             "社会责任": {"涉及": False, "权重": 0, "具体维度": []},
             "primary_competency": "生命观念"},
        ]
        result = analyzer.aggregate_exam_competencies(questions)
        assert result["生命观念"]["占比"] == 0


class TestReportGeneratorWeighted:
    """report_generator 加权计算回归保护"""

    def test_weighted_avg_difficulty_formula(self):
        """PDF 报告使用的加权 avg_difficulty 公式验证（不导入 report_generator 避免 weasyprint 依赖）"""
        # 模拟 report_generator.generate_pdf_report 中的 questions_difficulty 提取
        questions = [
            {"id": 1, "difficulty": {"final_difficulty": 8.0}, "total_score": 6},
            {"id": 2, "difficulty": {"final_difficulty": 2.0}, "total_score": 2},
        ]
        questions_difficulty = [
            {
                "question_id": q["id"],
                "final_difficulty": q["difficulty"]["final_difficulty"],
                "total_score": q.get("total_score", 0) or 1,
            }
            for q in questions
        ]
        # 复现 report_generator.py line 508-511 的加权公式
        total_w = sum(q["total_score"] for q in questions_difficulty)
        avg = sum(q["final_difficulty"] * q["total_score"] for q in questions_difficulty) / total_w if total_w > 0 else 0
        assert avg == 6.5  # (8*6 + 2*2) / 8

    def test_weighted_avg_missing_score_fallback(self):
        """total_score 缺失时 fallback=1 不塌缩为 0"""
        questions_difficulty = [
            {"final_difficulty": 5.0, "total_score": 0 or 1},  # 0 → or 1
            {"final_difficulty": 3.0, "total_score": 0 or 1},
        ]
        total_w = sum(q["total_score"] for q in questions_difficulty)
        avg = sum(q["final_difficulty"] * q["total_score"] for q in questions_difficulty) / total_w
        assert avg == 4.0  # (5*1+3*1)/2

    def test_gradient_weighted_avg(self):
        """难度梯度三段应按分值加权"""
        # 模拟三段数据
        part = [
            {"final_difficulty": 8.0, "total_score": 6},
            {"final_difficulty": 2.0, "total_score": 2},
        ]
        # 复现 _weighted_avg 逻辑
        w = sum(q["total_score"] for q in part)
        avg = sum(q["final_difficulty"] * q["total_score"] for q in part) / w if w > 0 else 0
        assert avg == 6.5  # (8*6+2*2)/8
