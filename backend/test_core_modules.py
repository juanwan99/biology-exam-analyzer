"""核心业务模块单元测试。

覆盖不依赖数据库的纯逻辑模块：
- utils.py (infer_question_type)
- session_manager.py (save/get/expire)
- calibration.py (calibrate/fit/piecewise)
- feature_extractor.py (parse_features/build_prompt)
- rule_scorer.py (score_to_label, _interpolate)
"""
import pytest
import json
import time
from datetime import datetime, timedelta
from unittest.mock import patch


# ============ utils.py ============

class TestInferQuestionType:
    """题型推断逻辑测试。"""

    def setup_method(self):
        from utils import infer_question_type
        self.infer = infer_question_type

    def test_known_type_passthrough(self):
        """已有明确题型时直接返回。"""
        q = {"question_type": "single_choice", "id": 1}
        assert self.infer(q) == "single_choice"

    def test_unknown_with_single_choice_header(self):
        """从分节标题推断单选。"""
        q = {"question_type": "unknown", "_section_header": "一、单项选择题", "id": 1}
        assert self.infer(q) == "single_choice"

    def test_unknown_with_multiple_choice_header(self):
        """从分节标题推断多选。"""
        q = {"question_type": "unknown", "_section_header": "二、不定项选择题", "id": 2}
        assert self.infer(q) == "multiple_choice"

    def test_unknown_with_fill_blank_header(self):
        """从分节标题推断填空。"""
        q = {"question_type": "unknown", "_section_header": "三、填空题", "id": 3}
        assert self.infer(q) == "fill_blank"

    def test_unknown_with_short_answer_header(self):
        """从分节标题推断简答。"""
        q = {"question_type": "unknown", "_section_header": "四、非选择题", "id": 4}
        assert self.infer(q) == "short_answer"

    def test_unknown_no_header(self):
        """无标题时返回 unknown。"""
        q = {"question_type": "unknown", "id": 5}
        assert self.infer(q) == "unknown"

    def test_missing_type_field(self):
        """缺少 question_type 字段时返回 unknown。"""
        q = {"id": 6}
        assert self.infer(q) == "unknown"

    def test_experiment_header(self):
        """实验类标题推断为简答。"""
        q = {"question_type": "unknown", "_section_header": "实验探究题", "id": 7}
        assert self.infer(q) == "short_answer"


# ============ session_manager.py ============

class TestSessionManager:
    """Session 管理测试。"""

    def setup_method(self):
        from session_manager import SESSION_STORAGE, save_session, get_session, clean_expired_sessions
        SESSION_STORAGE.clear()
        self.save = save_session
        self.get = get_session
        self.clean = clean_expired_sessions
        self.storage = SESSION_STORAGE

    def test_save_and_get(self):
        """保存后能取回。"""
        self.save("s1", {"questions": [1, 2, 3]})
        data = self.get("s1")
        assert data == {"questions": [1, 2, 3]}

    def test_get_nonexistent(self):
        """取不存在的 session 返回 None。"""
        assert self.get("nonexistent") is None

    def test_expired_session_cleaned(self):
        """过期 session 自动清理。"""
        self.storage["old"] = {
            "data": {"x": 1},
            "expire_time": datetime.now() - timedelta(minutes=1)
        }
        assert self.get("old") is None
        assert "old" not in self.storage

    def test_multiple_sessions(self):
        """多个 session 互不干扰。"""
        self.save("a", {"v": 1})
        self.save("b", {"v": 2})
        assert self.get("a")["v"] == 1
        assert self.get("b")["v"] == 2

    def test_overwrite_session(self):
        """同 ID 覆盖旧数据。"""
        self.save("s1", {"v": 1})
        self.save("s1", {"v": 2})
        assert self.get("s1")["v"] == 2


# ============ calibration.py ============

class TestCalibration:
    """难度校准测试。"""

    def test_no_model_passthrough(self):
        """无校准模型时原样返回。"""
        from calibration import calibrate, _calibration_fn
        import calibration
        calibration._calibration_fn = None
        # 确保模型文件不存在的情况下
        with patch.object(calibration, '_CALIBRATION_PATH') as mock_path:
            mock_path.exists.return_value = False
            assert calibrate(5.0) == 5.0
            assert calibrate(0.0) == 0.0

    def test_piecewise_interpolation(self):
        """分段线性插值。"""
        from calibration import _apply_piecewise
        model = {"x": [0.0, 5.0, 10.0], "y": [1.0, 5.0, 9.0]}
        assert _apply_piecewise(model, 0.0) == 1.0
        assert _apply_piecewise(model, 5.0) == 5.0
        assert _apply_piecewise(model, 10.0) == 9.0
        assert _apply_piecewise(model, 2.5) == 3.0  # 线性插值

    def test_piecewise_clamp(self):
        """超出范围时夹到边界。"""
        from calibration import _apply_piecewise
        model = {"x": [2.0, 8.0], "y": [3.0, 7.0]}
        assert _apply_piecewise(model, 0.0) == 3.0  # 低于最小
        assert _apply_piecewise(model, 100.0) == 7.0  # 高于最大


# ============ feature_extractor.py ============

class TestParseFeatures:
    """特征解析容错测试（补充 test_feature_difficulty.py 中已有的）。"""

    def setup_method(self):
        from feature_extractor import parse_features, DEFAULT_FEATURES, FEATURE_RANGES
        self.parse = parse_features
        self.defaults = DEFAULT_FEATURES
        self.ranges = FEATURE_RANGES

    def test_valid_json_all_fields(self):
        """完整有效 JSON。"""
        raw = json.dumps({
            "bloom": 4, "reasoning_steps": 6, "knowledge_breadth": 2,
            "info_density": 3, "novelty": 1, "question_type_factor": 2
        })
        result = self.parse(raw)
        assert result["bloom"] == 4
        assert result["reasoning_steps"] == 6

    def test_none_input(self):
        """None 输入返回默认值。"""
        result = self.parse(None)
        assert result == self.defaults

    def test_empty_string(self):
        """空字符串返回默认值。"""
        result = self.parse("")
        assert result == self.defaults

    def test_range_clipping_high(self):
        """超出上限被裁剪。"""
        raw = json.dumps({"bloom": 99, "reasoning_steps": 1, "knowledge_breadth": 1,
                          "info_density": 1, "novelty": 1, "question_type_factor": 1})
        result = self.parse(raw)
        assert result["bloom"] == 6  # max for bloom

    def test_range_clipping_low(self):
        """低于下限被裁剪。"""
        raw = json.dumps({"bloom": -5, "reasoning_steps": 0, "knowledge_breadth": 1,
                          "info_density": 1, "novelty": 1, "question_type_factor": 1})
        result = self.parse(raw)
        assert result["bloom"] == 1
        assert result["reasoning_steps"] == 1

    def test_missing_fields_use_defaults(self):
        """缺失字段用默认值补全。"""
        raw = json.dumps({"bloom": 5})
        result = self.parse(raw)
        assert result["bloom"] == 5
        assert result["reasoning_steps"] == self.defaults["reasoning_steps"]

    def test_reason_fields_preserved(self):
        """保留 reason 字段。"""
        raw = json.dumps({
            "bloom": 3, "bloom_reason": "需要理解概念",
            "reasoning_steps": 2, "knowledge_breadth": 1,
            "info_density": 1, "novelty": 1, "question_type_factor": 1
        })
        result = self.parse(raw)
        assert result["bloom_reason"] == "需要理解概念"

    def test_reason_truncated(self):
        """reason 字段超长被截断到 50 字符。"""
        raw = json.dumps({
            "bloom": 3, "bloom_reason": "x" * 100,
            "reasoning_steps": 2, "knowledge_breadth": 1,
            "info_density": 1, "novelty": 1, "question_type_factor": 1
        })
        result = self.parse(raw)
        assert len(result["bloom_reason"]) == 50

    def test_non_numeric_value_uses_default(self):
        """非数字值用默认值。"""
        raw = json.dumps({"bloom": "high", "reasoning_steps": 2, "knowledge_breadth": 1,
                          "info_density": 1, "novelty": 1, "question_type_factor": 1})
        result = self.parse(raw)
        assert result["bloom"] == self.defaults["bloom"]

    def test_json_in_markdown_code_block(self):
        """从 markdown code block 中提取。"""
        raw = '```json\n{"bloom": 5, "reasoning_steps": 3, "knowledge_breadth": 2, "info_density": 2, "novelty": 2, "question_type_factor": 3}\n```'
        result = self.parse(raw)
        assert result["bloom"] == 5

    def test_json_mixed_with_text(self):
        """从混合文本中提取第一个 JSON。"""
        raw = '分析如下：{"bloom": 4, "reasoning_steps": 5} 以上就是评分。'
        result = self.parse(raw)
        assert result["bloom"] == 4
        assert result["reasoning_steps"] == 5


class TestBuildFeaturePrompt:
    """Prompt 构建测试。"""

    def setup_method(self):
        from feature_extractor import build_feature_prompt
        self.build = build_feature_prompt

    def test_basic_prompt(self):
        """基本 prompt 包含题目文本。"""
        prompt = self.build("下列关于细胞的描述，正确的是")
        assert "下列关于细胞的描述，正确的是" in prompt
        assert "bloom" in prompt

    def test_with_options(self):
        """包含选项。"""
        prompt = self.build("题目", options="A.选项1 B.选项2")
        assert "选项：A.选项1 B.选项2" in prompt

    def test_with_answer(self):
        """包含正确答案。"""
        prompt = self.build("题目", correct_answer="A")
        assert "正确答案：A" in prompt

    def test_without_options_no_options_label(self):
        """无选项时不出现选项标签。"""
        prompt = self.build("简答题：描述光合作用过程")
        assert "选项：" not in prompt


# ============ rule_scorer.py 补充 ============

class TestRuleScorerExtended:
    """rule_scorer 补充测试。"""

    def setup_method(self):
        from rule_scorer import compute_difficulty, score_to_label, _interpolate

        self.compute = compute_difficulty
        self.label = score_to_label
        self.interp = _interpolate

    def test_interpolate_exact_key(self):
        """精确命中 key 值。"""
        mapping = {1: 0.0, 5: 0.5, 10: 1.0}
        assert self.interp(mapping, 5) == 0.5

    def test_interpolate_between(self):
        """两个 key 之间的插值。"""
        mapping = {1: 0.0, 10: 1.0}
        result = self.interp(mapping, 5.5)
        assert abs(result - 0.5) < 0.01

    def test_interpolate_below_min(self):
        """低于最小 key 返回最小值。"""
        mapping = {2: 0.1, 10: 1.0}
        assert self.interp(mapping, 0) == 0.1

    def test_interpolate_above_max(self):
        """高于最大 key 返回最大值。"""
        mapping = {1: 0.0, 5: 1.0}
        assert self.interp(mapping, 100) == 1.0

    def test_label_boundaries(self):
        """标签边界值。"""
        assert self.label(3.0) == "简单"
        assert self.label(3.1) == "中等偏易"
        assert self.label(5.0) == "中等偏易"
        assert self.label(5.1) == "中等偏难"
        assert self.label(7.0) == "中等偏难"
        assert self.label(7.1) == "困难"

    def test_monotonicity(self):
        """难度随特征值单调递增。"""
        base = {"bloom": 1, "reasoning_steps": 1, "knowledge_breadth": 1,
                "info_density": 1, "novelty": 1, "question_type_factor": 1}
        scores = []
        for bloom in [1, 2, 3, 4, 5]:
            f = dict(base, bloom=bloom)
            scores.append(self.compute(f))
        for i in range(len(scores) - 1):
            assert scores[i] <= scores[i + 1], f"bloom {i+1}→{i+2}: {scores[i]} > {scores[i+1]}"
