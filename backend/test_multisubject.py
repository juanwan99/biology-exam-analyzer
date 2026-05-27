import os
import pytest

__test__ = False

pytestmark = pytest.mark.skipif(
    not os.environ.get("DEEPSEEK_API_KEY"),
    reason="需要 DEEPSEEK_API_KEY 环境变量（集成测试）"
)

"""多学科端到端验证脚本 — 直接调用 pipeline，跳过 API/认证层。"""
import asyncio
import json
import sys

# 在 backend 目录运行
from difficulty_pipeline import DifficultyPipeline
from prompt_loader import PromptLoader

# ========== 测试用例 ==========

QUESTIONS = {
    "chemistry": {
        "content": """下列关于Na2O2的叙述正确的是
A. Na2O2是碱性氧化物
B. Na2O2与水反应生成NaOH和O2，Na2O2是还原剂
C. Na2O2与CO2反应生成Na2CO3和O2，可用于呼吸面具供氧
D. Na2O2的电子式为Na+[:O:O:]2-Na+""",
        "question_type": "选择题",
        "correct_answer": "C",
        "total_score": 3,
        "subject": "chemistry",
    },
    "chemistry_big": {
        "content": """某化工厂以粗盐（含少量MgCl2、CaCl2、Na2SO4）为原料制备精盐。
(1) 写出除去MgCl2的化学方程式。（2分）
(2) 加入Na2CO3的目的是什么？为什么要"先加Na2CO3再加NaOH"？（4分）
(3) 如何检验SO42-已完全除去？写出操作步骤和现象。（4分）
(4) 最后为什么要加适量盐酸？（2分）""",
        "question_type": "实验题",
        "correct_answer": "见解析",
        "total_score": 12,
        "subject": "chemistry",
    },
    "history": {
        "content": """有学者认为，"五四运动是第一次历史巨变的补课，又是第二次历史巨变的起点。"这里"第二次历史巨变"是指
A. 辛亥革命推翻帝制
B. 新中国的成立
C. 三大改造的完成
D. 改革开放""",
        "question_type": "选择题",
        "correct_answer": "B",
        "total_score": 4,
        "subject": "history",
    },
    "cz-physics": {
        "content": "小明用弹簧测力计测量一个物体的重力，读数为4.8N。该物体的质量是多少千克？（g取10N/kg）",
        "question_type": "计算题",
        "correct_answer": "0.48kg",
        "total_score": 4,
        "subject": "cz-physics",
    },
}


async def test_subject(name, question):
    """测试单个学科。"""
    print(f"\n{'='*60}")
    print(f"学科: {name} (subject={question['subject']})")
    print(f"题目: {question['content'][:80]}...")
    print(f"{'='*60}")

    # 1. 验证 PromptLoader 能加载
    loader = PromptLoader(question["subject"])
    assert loader.exists("feature_extractor"), f"{name}: feature_extractor.txt 不存在!"
    prompt_preview = loader.load("feature_extractor",
                                 question_block="测试题目",
                                 qtype_hint="")[:100]
    print(f"Prompt 前 100 字: {prompt_preview}")

    # 2. 调用 pipeline
    pipeline = DifficultyPipeline()
    try:
        result = await pipeline.evaluate_with_refinement(question)
        print(f"\n结果:")
        print(f"  难度分数: {result['final_difficulty']}")
        print(f"  难度标签: {result['difficulty_label']}")
        print(f"  置信度:   {result['confidence']}")
        print(f"  flags:    {result.get('flags', [])}")

        features = result.get("features", {})
        if features:
            print(f"  working_memory:    {features.get('working_memory')}")
            print(f"  reasoning_steps:   {features.get('reasoning_steps')}")
            print(f"  chain_coupling:    {features.get('chain_coupling')}")
            print(f"  trap_density:      {features.get('trap_density')}")
            print(f"  novelty:           {features.get('novelty')}")
            print(f"  knowledge_breadth: {features.get('knowledge_breadth')}")
            if "_big_question" in features:
                bq = features["_big_question"]
                print(f"  [大题] 小问数: {len(bq['subquestions'])}, "
                      f"依赖数: {len(bq['dependencies'])}, "
                      f"effective_steps: {bq['effective_steps']}")

        return True, result['final_difficulty']
    except Exception as e:
        print(f"  ❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        return False, 0


async def main():
    results = {}
    for name, question in QUESTIONS.items():
        ok, score = await test_subject(name, question)
        results[name] = {"ok": ok, "score": score}

    print(f"\n{'='*60}")
    print("汇总:")
    for name, r in results.items():
        status = "✅" if r["ok"] else "❌"
        print(f"  {status} {name}: {r['score']}")
    print(f"{'='*60}")

    all_ok = all(r["ok"] for r in results.values())
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    asyncio.run(main())
