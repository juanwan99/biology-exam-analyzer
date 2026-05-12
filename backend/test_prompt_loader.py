"""PromptLoader 单元测试。"""
import pytest
from pathlib import Path
from prompt_loader import PromptLoader


class TestPromptLoader:
    """PromptLoader 加载和渲染测试。"""

    def test_load_biology_feature_extractor(self):
        """加载生物 feature_extractor prompt。"""
        loader = PromptLoader("biology")
        prompt = loader.load("feature_extractor",
                            question_block="某生物题目",
                            qtype_hint="\n题型：选择题")
        assert "某生物题目" in prompt
        assert "选择题" in prompt

    def test_load_chemistry_feature_extractor(self):
        """加载化学 feature_extractor prompt。"""
        loader = PromptLoader("chemistry")
        prompt = loader.load("feature_extractor",
                            question_block="某化学题目",
                            qtype_hint="")
        assert "某化学题目" in prompt
        assert "化学" in prompt

    def test_load_history(self):
        """加载历史 prompt。"""
        loader = PromptLoader("history")
        assert loader.exists("feature_extractor")

    def test_load_chinese(self):
        """加载语文 prompt。"""
        loader = PromptLoader("chinese")
        assert loader.exists("feature_extractor")

    def test_nonexistent_subject_fallback(self):
        """不存在的学科 fallback 到 _base（如果存在）或抛异常。"""
        loader = PromptLoader("nonexistent_subject_xyz")
        with pytest.raises(FileNotFoundError):
            loader.load("feature_extractor")

    def test_exists_true(self):
        """exists 返回 True。"""
        loader = PromptLoader("biology")
        assert loader.exists("feature_extractor") is True

    def test_exists_false(self):
        """不存在的 prompt 返回 False。"""
        loader = PromptLoader("biology")
        assert loader.exists("nonexistent_prompt") is False

    def test_load_without_variables(self):
        """无变量模板直接返回原文。"""
        loader = PromptLoader("biology")
        prompt = loader.load("split_prompt")
        assert len(prompt) > 0
