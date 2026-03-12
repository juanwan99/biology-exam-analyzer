# 特征分析难度评估 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用特征提取+规则评分替代模拟学生+IRT，消除 floor_hit 问题

**Architecture:** 单次 LLM 调用提取 6 维题目特征（bloom/steps/breadth/density/novelty/qtype），加权线性公式计算 0-10 难度分。`difficulty_pipeline.py` 的 Stage 2/3 替换，对外接口不变。

**Tech Stack:** Python 3, Claude Sonnet (via claude_client.py), FastAPI (existing)

**Design doc:** `docs/plans/2026-03-12-feature-difficulty-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `backend/rule_scorer.py` | Create | 加权公式 + 标签映射（纯计算，无 I/O） |
| `backend/feature_extractor.py` | Create | LLM prompt 构建 + JSON 解析 + 容错 |
| `backend/difficulty_pipeline.py` | Modify | Stage 2/3 替换为 feature_extractor + rule_scorer |
| `backend/test_feature_difficulty.py` | Create | 集成测试：10 道真题端到端验证 |

---

## Chunk 1: 规则评分引擎 + 特征提取 + Pipeline 集成

### Task 1: rule_scorer.py — 加权公式

**Files:**
- Create: `backend/rule_scorer.py`
- Test: `backend/test_feature_difficulty.py`

- [ ] **Step 1: Write the failing test**

在服务器 `/home/ubuntu/biology-exam-analyzer/backend/test_feature_difficulty.py` 创建：

```python
"""特征分析难度评估测试。"""
import pytest
from rule_scorer import compute_difficulty, score_to_label


class TestComputeDifficulty:
    """compute_difficulty 加权公式测试。"""

    def test_easiest_question(self):
        """纯识记单选题 → 约 2.3 分。"""
        features = {
            "bloom": 1,
            "reasoning_steps": 1,
            "knowledge_breadth": 1,
            "info_density": 1,
            "novelty": 1,
            "question_type_factor": 1,
        }
        score = compute_difficulty(features)
        assert 2.0 <= score <= 3.0, f"最简单题应在 2-3 分，实际 {score}"

    def test_hardest_question(self):
        """跨模块实验设计题 → 约 9.6 分。"""
        features = {
            "bloom": 5,
            "reasoning_steps": 10,
            "knowledge_breadth": 3,
            "info_density": 3,
            "novelty": 3,
            "question_type_factor": 4,
        }
        score = compute_difficulty(features)
        assert 9.0 <= score <= 10.0, f"最难题应在 9-10 分，实际 {score}"

    def test_medium_question(self):
        """中等难度题 → 4-6 分。"""
        features = {
            "bloom": 3,
            "reasoning_steps": 3,
            "knowledge_breadth": 2,
            "info_density": 2,
            "novelty": 2,
            "question_type_factor": 1,
        }
        score = compute_difficulty(features)
        assert 4.0 <= score <= 6.0, f"中等题应在 4-6 分，实际 {score}"

    def test_steps_capped_at_8(self):
        """reasoning_steps 超过 8 应封顶。"""
        f8 = {"bloom": 3, "reasoning_steps": 8, "knowledge_breadth": 2,
              "info_density": 2, "novelty": 2, "question_type_factor": 1}
        f20 = dict(f8, reasoning_steps=20)
        assert compute_difficulty(f8) == compute_difficulty(f20)


class TestScoreToLabel:
    def test_labels(self):
        assert score_to_label(2.0) == "简单"
        assert score_to_label(4.0) == "中等偏易"
        assert score_to_label(6.0) == "中等偏难"
        assert score_to_label(8.0) == "困难"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/ubuntu/biology-exam-analyzer/backend && python -m pytest test_feature_difficulty.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'rule_scorer'`

- [ ] **Step 3: Write minimal implementation**

Create `backend/rule_scorer.py`:

```python
"""规则评分引擎 — 6 维特征加权公式。

设计文档: docs/plans/2026-03-12-feature-difficulty-design.md §4
"""


def compute_difficulty(features: dict) -> float:
    """6 维特征 → 0-10 难度分。

    Args:
        features: dict with keys bloom, reasoning_steps, knowledge_breadth,
                  info_density, novelty, question_type_factor

    Returns:
        float: 0.0-10.0 难度分数，保留 1 位小数
    """
    bloom = features["bloom"]
    steps = features["reasoning_steps"]
    breadth = features["knowledge_breadth"]
    density = features["info_density"]
    novelty = features["novelty"]
    qtype = features["question_type_factor"]

    raw = (
        (bloom / 6) * 0.25
        + min(steps / 8, 1.0) * 0.25
        + (breadth / 3) * 0.15
        + (density / 3) * 0.15
        + (novelty / 3) * 0.10
        + (qtype / 4) * 0.10
    )
    return round(raw * 10, 1)


def score_to_label(score: float) -> str:
    """分数 → 难度标签（与 irt_estimator 一致）。"""
    if score <= 3.0:
        return "简单"
    elif score <= 5.0:
        return "中等偏易"
    elif score <= 7.0:
        return "中等偏难"
    else:
        return "困难"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/ubuntu/biology-exam-analyzer/backend && python -m pytest test_feature_difficulty.py::TestComputeDifficulty -v && python -m pytest test_feature_difficulty.py::TestScoreToLabel -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /home/ubuntu/biology-exam-analyzer
git add backend/rule_scorer.py backend/test_feature_difficulty.py
git commit -m "feat: add rule_scorer — weighted formula for feature-based difficulty"
```

**审查清单:**
- ✓ compute_difficulty 返回值在 0-10 范围内（最低 2.3，最高 9.6）
- ✓ reasoning_steps 超过 8 封顶（min(steps/8, 1.0)）
- ✓ score_to_label 标签与 irt_estimator._score_to_label 一致
- ✗ 不应该有负数或 >10 的输出（公式保证 raw∈[0,1]）
- 关键行为：纯函数，无 I/O，无副作用

---

### Task 2: feature_extractor.py — LLM 特征提取

**Files:**
- Create: `backend/feature_extractor.py`
- Test: `backend/test_feature_difficulty.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `test_feature_difficulty.py`:

```python
import json
from feature_extractor import parse_features, build_feature_prompt, DEFAULT_FEATURES


class TestParseFeatures:
    """JSON 解析容错测试。"""

    def test_valid_json(self):
        raw = '{"bloom": 3, "reasoning_steps": 4, "knowledge_breadth": 2, "info_density": 2, "novelty": 1, "question_type_factor": 1}'
        result = parse_features(raw)
        assert result["bloom"] == 3
        assert result["reasoning_steps"] == 4

    def test_json_in_code_block(self):
        raw = '```json\n{"bloom": 2, "reasoning_steps": 1, "knowledge_breadth": 1, "info_density": 1, "novelty": 1, "question_type_factor": 1}\n```'
        result = parse_features(raw)
        assert result["bloom"] == 2

    def test_out_of_range_clipped(self):
        raw = '{"bloom": 10, "reasoning_steps": -1, "knowledge_breadth": 5, "info_density": 0, "novelty": 3, "question_type_factor": 1}'
        result = parse_features(raw)
        assert result["bloom"] == 6  # clipped to max
        assert result["reasoning_steps"] == 1  # clipped to min
        assert result["knowledge_breadth"] == 3  # clipped to max
        assert result["info_density"] == 1  # clipped to min

    def test_unparseable_returns_default(self):
        result = parse_features("这道题很难blahblah")
        assert result == DEFAULT_FEATURES

    def test_partial_json_extracts_what_it_can(self):
        """部分字段缺失 → 用默认值补全。"""
        raw = '{"bloom": 4, "reasoning_steps": 3}'
        result = parse_features(raw)
        assert result["bloom"] == 4
        assert result["reasoning_steps"] == 3
        assert result["knowledge_breadth"] == DEFAULT_FEATURES["knowledge_breadth"]


class TestBuildPrompt:
    def test_prompt_contains_question(self):
        prompt = build_feature_prompt("下列关于DNA的说法...", "A.xx B.xx", "A")
        assert "下列关于DNA的说法" in prompt
        assert "A.xx B.xx" in prompt
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/ubuntu/biology-exam-analyzer/backend && python -m pytest test_feature_difficulty.py::TestParseFeatures -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'feature_extractor'`

- [ ] **Step 3: Write minimal implementation**

Create `backend/feature_extractor.py`:

```python
"""LLM 特征提取 — prompt 构建 + JSON 解析容错。

设计文档: docs/plans/2026-03-12-feature-difficulty-design.md §5
"""
import json
import re
import logging
from claude_client import send_message

logger = logging.getLogger(__name__)

# 各维度的合法范围 (min, max)
FEATURE_RANGES = {
    "bloom": (1, 6),
    "reasoning_steps": (1, 10),
    "knowledge_breadth": (1, 3),
    "info_density": (1, 3),
    "novelty": (1, 3),
    "question_type_factor": (1, 4),
}

# 解析失败时的默认值（各维度中位数）
DEFAULT_FEATURES = {
    "bloom": 3,
    "reasoning_steps": 4,
    "knowledge_breadth": 2,
    "info_density": 2,
    "novelty": 2,
    "question_type_factor": 1,
}


def build_feature_prompt(question_text: str, options: str = "", correct_answer: str = "") -> str:
    """构建特征提取 prompt。"""
    parts = [question_text]
    if options:
        parts.append(f"选项：{options}")
    if correct_answer:
        parts.append(f"正确答案：{correct_answer}")
    question_block = "\n".join(parts)

    return f"""你是一名资深高中生物教师。请分析这道题目的难度特征。

题目：
{question_block}

请输出以下 6 个维度的评分（严格 JSON，不要解释）：
{{
  "bloom": 1-6（1识记 2理解 3应用 4分析 5评价 6创造），
  "reasoning_steps": 正整数（从题目信息到答案的推理步数），
  "knowledge_breadth": 1-3（1单知识点 2跨考点 3跨模块），
  "info_density": 1-3（1低≤2条 2中3-5条 3高>5条或含图表），
  "novelty": 1-3（1教材原文 2变式 3全新情境），
  "question_type_factor": 1-4（1单选 2多选/填空 3简答 4实验设计）
}}"""


def parse_features(raw: str) -> dict:
    """从 LLM 原始输出解析 6 维特征，带容错和范围裁剪。

    解析策略：
    1. 直接 JSON 解析
    2. 从 markdown code block 提取
    3. 正则提取第一个 JSON object
    4. 全部失败 → 返回默认值
    """
    data = None

    # 策略 1: 直接解析
    try:
        data = json.loads(raw.strip())
    except (json.JSONDecodeError, TypeError):
        pass

    # 策略 2: code block
    if data is None:
        m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(1))
            except json.JSONDecodeError:
                pass

    # 策略 3: 第一个 JSON object
    if data is None:
        m = re.search(r'\{[^{}]*\}', raw)
        if m:
            try:
                data = json.loads(m.group())
            except json.JSONDecodeError:
                pass

    # 全部失败
    if not isinstance(data, dict):
        logger.warning(f"特征解析失败，使用默认值。原始输出: {raw[:200]}")
        return dict(DEFAULT_FEATURES)

    # 补全缺失字段 + 范围裁剪
    result = {}
    for key, (lo, hi) in FEATURE_RANGES.items():
        val = data.get(key, DEFAULT_FEATURES[key])
        try:
            val = int(val)
        except (ValueError, TypeError):
            val = DEFAULT_FEATURES[key]
        result[key] = max(lo, min(hi, val))

    return result


async def extract_features(question_text: str, options: str = "",
                           correct_answer: str = "") -> dict:
    """调用 LLM 提取题目特征。

    Returns:
        dict: 6 维特征值
    """
    prompt = build_feature_prompt(question_text, options, correct_answer)
    try:
        raw = await send_message(
            prompt,
            model="claude-sonnet-4-5-20250929",
            max_tokens=256,
            temperature=0,
        )
        return parse_features(raw)
    except Exception as e:
        logger.error(f"特征提取 API 调用失败: {e}")
        return dict(DEFAULT_FEATURES)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/ubuntu/biology-exam-analyzer/backend && python -m pytest test_feature_difficulty.py::TestParseFeatures test_feature_difficulty.py::TestBuildPrompt -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /home/ubuntu/biology-exam-analyzer
git add backend/feature_extractor.py backend/test_feature_difficulty.py
git commit -m "feat: add feature_extractor — LLM prompt + JSON parsing with fallback"
```

**审查清单:**
- ✓ parse_features 对 3 种 JSON 格式都能解析（直接/code block/嵌入）
- ✓ 越界值被 clip 到合法范围
- ✓ 全部解析失败返回 DEFAULT_FEATURES（不抛异常）
- ✓ API 调用失败返回默认值而非崩溃
- ✗ 不应该有 KeyError（缺失字段用默认值补全）
- 关键行为：extract_features 用 temperature=0 确保稳定输出

---

### Task 3: difficulty_pipeline.py — Stage 2/3 替换

**Files:**
- Modify: `backend/difficulty_pipeline.py` (lines 1-140)
- Test: `backend/test_feature_difficulty.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `test_feature_difficulty.py`:

```python
import asyncio
from unittest.mock import patch, AsyncMock
from difficulty_pipeline import DifficultyPipeline


class TestPipelineIntegration:
    """Pipeline 集成测试（mock LLM 调用）。"""

    def test_evaluate_returns_expected_fields(self):
        """验证返回字段兼容旧接口。"""
        mock_features = {
            "bloom": 3, "reasoning_steps": 4, "knowledge_breadth": 2,
            "info_density": 2, "novelty": 2, "question_type_factor": 1,
        }
        with patch("difficulty_pipeline.extract_features", new_callable=AsyncMock, return_value=mock_features):
            pipeline = DifficultyPipeline()
            result = asyncio.get_event_loop().run_until_complete(
                pipeline.evaluate_with_refinement({
                    "content": "下列关于DNA的说法正确的是",
                    "question_type": "选择题",
                    "correct_answer": "A",
                    "total_score": 2,
                })
            )

        # 旧字段必须存在
        assert "base_difficulty" in result
        assert "final_difficulty" in result
        assert "difficulty_label" in result
        assert "score_distribution_by_difficulty" in result
        # 新字段
        assert "features" in result
        assert result["features"]["bloom"] == 3
        # 分数合理
        assert 0 <= result["base_difficulty"] <= 10

    def test_empty_content_returns_default(self):
        pipeline = DifficultyPipeline()
        result = asyncio.get_event_loop().run_until_complete(
            pipeline.evaluate_with_refinement({"content": "", "question_type": "", "correct_answer": "", "total_score": 1})
        )
        assert result["difficulty_label"] == "未评估"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/ubuntu/biology-exam-analyzer/backend && python -m pytest test_feature_difficulty.py::TestPipelineIntegration -v`
Expected: FAIL (current pipeline doesn't have `features` field, doesn't import `extract_features`)

- [ ] **Step 3: Modify difficulty_pipeline.py**

Replace the import section and `_evaluate_single` method. Keep `__init__`, `_default_result`, `_score_distribution`, `evaluate_with_refinement`, `evaluate_with_refinement_sync` signatures intact.

Changes:
1. Replace `from simulated_student import ...` and `from irt_estimator import ...` with new imports
2. Rewrite `_evaluate_single` to use feature extraction + rule scoring
3. Update `_default_result` to include `features` field
4. Keep `_score_distribution` unchanged

New `difficulty_pipeline.py` content:

```python
"""难度量化 Pipeline 主控 — 特征分析评分。

v2: 特征提取 + 规则评分（替代模拟学生 + IRT）
设计文档: docs/plans/2026-03-12-feature-difficulty-design.md
"""
import asyncio
import logging
from feature_extractor import extract_features
from rule_scorer import compute_difficulty, score_to_label

logger = logging.getLogger(__name__)


class DifficultyPipeline:
    """难度量化 Pipeline。v2: 特征分析。"""

    def __init__(self, **kwargs):
        """初始化。接受 kwargs 以兼容旧调用方 DifficultyEngine(gemini_analyzer=...) 签名。"""
        pass

    async def _evaluate_single(self, question: dict, **kwargs) -> dict:
        """评估单道题难度。

        Args:
            question: dict，需包含 content, question_type, correct_answer, total_score
            **kwargs: 兼容旧接口，忽略 mode/analysis_result

        Returns:
            dict: 兼容旧接口 + 新增 features 字段
        """
        question_text = question.get("content", "")
        question_type = question.get("question_type", "")
        correct_answer = question.get("correct_answer", "")
        total_score = float(question.get("total_score", 1))
        options = question.get("options", "")

        if not question_text:
            logger.warning("题目内容为空，跳过难度评估")
            return self._default_result()

        # 拼接选项到题目文本（exercise_bank 中 options 是独立字段）
        full_text = question_text
        if options:
            full_text = f"{question_text}\n{options}"

        # Stage 2 (new): LLM 特征提取
        logger.info(f"开始特征提取: {question_text[:50]}...")
        features = await extract_features(full_text, "", correct_answer)
        logger.info(f"特征提取完成: {features}")

        # Stage 3 (new): 规则评分
        score = compute_difficulty(features)
        label = score_to_label(score)
        logger.info(f"规则评分: {score} ({label})")

        return {
            # 旧字段（main.py / prediction_service.py 消费）
            "base_difficulty": score,
            "final_difficulty": score,
            "difficulty_label": label,
            "score_distribution_by_difficulty": self._score_distribution(score, total_score),
            # 新字段
            "features": features,
            "confidence": 0.7,  # 规则评分固定置信度，后续校准后动态调整
            "predicted_score_rate": None,
            "flags": [],
        }

    def _default_result(self):
        """无法评估时的默认返回。"""
        return {
            "base_difficulty": 5.0,
            "final_difficulty": 5.0,
            "difficulty_label": "未评估",
            "score_distribution_by_difficulty": {},
            "features": None,
            "confidence": 0.0,
            "predicted_score_rate": None,
            "flags": ["no_evaluation"],
        }

    def _score_distribution(self, difficulty_score: float, total_score: float) -> dict:
        """从难度分数推导按难度等级的分值分布（兼容旧格式：中文 key）。"""
        if difficulty_score <= 3:
            weights = {"简单": 0.7, "中等": 0.2, "困难": 0.1}
        elif difficulty_score <= 5:
            weights = {"简单": 0.3, "中等": 0.5, "困难": 0.2}
        elif difficulty_score <= 7:
            weights = {"简单": 0.1, "中等": 0.4, "困难": 0.5}
        else:
            weights = {"简单": 0.05, "中等": 0.25, "困难": 0.7}
        return {k: round(v * total_score, 1) for k, v in weights.items()}

    async def evaluate_with_refinement(self, question: dict, **kwargs) -> dict:
        """兼容旧接口名。直接调用 _evaluate_single。"""
        return await self._evaluate_single(question, **kwargs)

    def evaluate_with_refinement_sync(self, question: dict, **kwargs) -> dict:
        """同步版本，供非 async 调用方使用。"""
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(self._evaluate_single(question, **kwargs))
        finally:
            loop.close()
```

- [ ] **Step 4: Run all tests**

Run: `cd /home/ubuntu/biology-exam-analyzer/backend && python -m pytest test_feature_difficulty.py -v`
Expected: All 12 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /home/ubuntu/biology-exam-analyzer
git add backend/difficulty_pipeline.py backend/test_feature_difficulty.py
git commit -m "feat: replace simulated student pipeline with feature extraction + rule scoring"
```

**审查清单:**
- ✓ `evaluate_with_refinement` 返回字段包含旧字段（base_difficulty, final_difficulty, difficulty_label, score_distribution_by_difficulty）
- ✓ `_default_result` 包含新增 `features` 字段
- ✓ options 拼接到 full_text（exercise_bank 的 options 是独立字段）
- ✓ 无 correct_answer 时仍可评估（不像旧 pipeline 必须有答案才能评判）
- ✗ 不应该引用 simulated_student 或 irt_estimator（已移除 import）
- ✗ main.py 消费的旧字段名不能变（base_difficulty, final_difficulty 等）
- 关键行为：`_evaluate_single` 内无 correct_answer 检查——特征提取不依赖答案是否存在（与旧 pipeline 不同）

---

### Task 4: 真题端到端验证（10 道题）

**Files:**
- None (script execution, no file changes)

- [ ] **Step 1: 从 exercise_bank 选 10 道覆盖不同难度的题**

SSH 到 jdcloud，执行 SQL 选题：

```bash
ssh jdcloud
cd /home/ubuntu/biology-exam-analyzer/backend
PGPASSWORD=biology123 psql -h localhost -U biology -d biology_edu -c "
SELECT id, LEFT(content, 80) as content_preview, question_type, difficulty_level
FROM exercise_bank
WHERE correct_answer IS NOT NULL AND correct_answer != ''
ORDER BY difficulty_level DESC
LIMIT 10;
"
```

- [ ] **Step 2: 运行 10 道题的特征提取+评分**

创建临时脚本 `/tmp/test_10q.py`：

```python
"""10 道真题端到端验证。"""
import asyncio
import sys
sys.path.insert(0, "/home/ubuntu/biology-exam-analyzer/backend")

import os
os.chdir("/home/ubuntu/biology-exam-analyzer/backend")

# 加载 .env
from dotenv import load_dotenv
load_dotenv("/home/ubuntu/biology-exam-analyzer/.env")

import psycopg2
from feature_extractor import extract_features
from rule_scorer import compute_difficulty, score_to_label


async def main():
    conn = psycopg2.connect(
        host="localhost", dbname="biology_edu",
        user="biology", password="biology123"
    )
    cur = conn.cursor()

    # 选 10 道覆盖不同难度的题
    cur.execute("""
        SELECT id, content, options, correct_answer, question_type, difficulty_level
        FROM exercise_bank
        WHERE correct_answer IS NOT NULL AND correct_answer != ''
        ORDER BY difficulty_level DESC
        LIMIT 10
    """)
    rows = cur.fetchall()

    print(f"{'ID':>4} {'旧难度':>6} {'新分数':>6} {'标签':>8} | 特征")
    print("-" * 80)

    for row in rows:
        qid, content, options, answer, qtype, old_diff = row
        full_text = content
        if options:
            full_text = f"{content}\n{options}"

        features = await extract_features(full_text, "", answer or "")
        score = compute_difficulty(features)
        label = score_to_label(score)
        old = old_diff if old_diff else "N/A"

        print(f"{qid:>4} {str(old):>6} {score:>6.1f} {label:>8} | B={features['bloom']} S={features['reasoning_steps']} Br={features['knowledge_breadth']} D={features['info_density']} N={features['novelty']} Q={features['question_type_factor']}")

    cur.close()
    conn.close()

asyncio.run(main())
```

Run: `ssh jdcloud 'cd /home/ubuntu/biology-exam-analyzer/backend && python3 /tmp/test_10q.py'`

Expected: 表格输出 10 道题的新旧难度对比。验收标准：
- 新分数分布不聚集（不像旧系统 77% 在 0.60）
- 分数区间合理（2-9 分）
- 无 API 报错

- [ ] **Step 3: 检查结果合理性并记录**

人工检查：
- 遗传计算题应该得分 > 简单识记题
- 实验设计题应该 > 选择题
- 分数分布是否有区分度

如有异常：检查特征提取 prompt 是否需要调整。

- [ ] **Step 4: Commit test script (optional)**

如果验证通过，可选提交验证脚本作为记录：
```bash
# 不提交临时脚本，只提交测试文件
```

**审查清单:**
- ✓ 10 道题覆盖不同 difficulty_level
- ✓ API 调用无 429 限流（单次顺序调用）
- ✗ 不应该出现全部默认值（说明 LLM 返回解析失败）
- 关键行为：与旧 difficulty_level 对比确认趋势一致

---

### Task 5: 移除旧 pipeline 的 correct_answer 硬性要求

**Files:**
- Modify: `backend/difficulty_pipeline.py`

- [ ] **Step 1: 确认旧 pipeline 有 correct_answer 检查**

旧代码 `_evaluate_single` 中有：
```python
if not correct_answer:
    logger.warning("无标准答案，跳过难度评估（无法评判对错）")
    return self._default_result()
```

特征分析不需要答案也能评估（答案只是辅助信息），但保留答案传递给 LLM 可以提高准确性。

- [ ] **Step 2: 移除硬性检查**

在新 `_evaluate_single` 中确认已无 `if not correct_answer: return default` 检查。如果 Task 3 的代码已正确，此步骤是确认性的。

- [ ] **Step 3: 验证无答案题也能评估**

Append to `test_feature_difficulty.py`:

```python
    def test_no_answer_still_evaluates(self):
        """无答案时仍能评估（不像旧 pipeline 直接返回默认）。"""
        mock_features = {
            "bloom": 2, "reasoning_steps": 2, "knowledge_breadth": 1,
            "info_density": 1, "novelty": 1, "question_type_factor": 1,
        }
        with patch("difficulty_pipeline.extract_features", new_callable=AsyncMock, return_value=mock_features):
            pipeline = DifficultyPipeline()
            result = asyncio.get_event_loop().run_until_complete(
                pipeline.evaluate_with_refinement({
                    "content": "描述光合作用的过程",
                    "question_type": "简答题",
                    "correct_answer": "",  # 无答案
                    "total_score": 6,
                })
            )
        assert result["difficulty_label"] != "未评估"
        assert result["features"] is not None
```

Run: `cd /home/ubuntu/biology-exam-analyzer/backend && python -m pytest test_feature_difficulty.py::TestPipelineIntegration::test_no_answer_still_evaluates -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
cd /home/ubuntu/biology-exam-analyzer
git add backend/test_feature_difficulty.py
git commit -m "test: verify no-answer questions still get difficulty evaluation"
```

**审查清单:**
- ✓ 无答案题不返回"未评估"
- ✓ main.py 调用方传入 correct_answer="" 时不会崩溃
- 关键行为：特征分析的核心优势之一——不依赖答案

---

### Task 6: main.py 兼容性确认

**Files:**
- Read only: `backend/main.py` (lines consuming difficulty result)

- [ ] **Step 1: 检查 main.py 消费的字段**

Grep main.py 中所有读取 difficulty_result 的字段：
```bash
ssh jdcloud 'grep -n "difficulty_result\[" /home/ubuntu/biology-exam-analyzer/backend/main.py'
```

- [ ] **Step 2: 确认兼容性**

检查旧字段是否都在新返回值中：
- `difficulty_result["base_difficulty"]` ✓
- `difficulty_result["final_difficulty"]` ✓
- `difficulty_result["difficulty_label"]` ✓
- `difficulty_result["score_distribution_by_difficulty"]` ✓

旧字段已移除但 main.py 可能引用：
- `difficulty_result["simulated_responses"]` — 检查是否被引用
- `difficulty_result["irt_params"]` — 检查是否被引用
- `difficulty_result["irt_difficulty"]` — 检查是否被引用

如果 main.py 引用了已移除字段 → 需要修改（添加兼容或修改 main.py）。

- [ ] **Step 3: 修复兼容性问题（如有）**

根据 Step 2 的发现修复。可能需要在 `_evaluate_single` 返回值中补充缺失字段为 None。

- [ ] **Step 4: pm2 重启并验证**

```bash
ssh jdcloud 'cd /home/ubuntu/biology-exam-analyzer && pm2 restart biology-analyzer'
# 等 5 秒后检查日志
ssh jdcloud 'pm2 logs biology-analyzer --lines 20 --nostream'
```

Expected: 服务正常启动，无 import 错误

- [ ] **Step 5: Commit (if changes made)**

```bash
cd /home/ubuntu/biology-exam-analyzer
git add -u
git commit -m "fix: ensure pipeline output compatible with main.py field consumption"
```

**审查清单:**
- ✓ main.py 引用的每个 difficulty_result 字段都在新返回值中
- ✓ pm2 重启后无启动错误
- ✗ 不应该修改 main.py 的消费逻辑（只改 pipeline 输出兼容）
- 关键行为：零中断部署——旧前端不感知后端变更
