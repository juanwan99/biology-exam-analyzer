"""
测试难度评估引擎的快速/深度双模式
"""
from difficulty_engine import DifficultyEngine
import time

# 测试题目
test_question = {
    "id": 7,
    "content": """某动物家系的系谱图如图所示。a1、a2、a3、a4是位于X染色体上的等位基因，
Ⅰ-1基因型为XalXa2，Ⅰ-2基因型为Xa3Y，Ⅱ-1和Ⅱ-4基因型均为Xa4Y，
Ⅳ-1为纯合子的概率为（    ）
A. 3/64  B. 3/32  C. 1/8  D. 3/16""",
    "knowledge_points": ["伴性遗传", "概率计算", "基因型推导"],
    "images": []
}

# 初始化引擎（无Gemini，仅测试快速模式）
engine = DifficultyEngine(rules_path="rules/difficulty_rules.json")

print("=" * 80)
print("🧪 测试难度评估引擎 - 双模式对比")
print("=" * 80)

# 测试快速模式
print("\n【快速模式 🚄】（仅规则引擎）")
print("-" * 80)
start_time = time.time()
fast_result = engine.evaluate_with_refinement(test_question, mode="fast")
fast_time = time.time() - start_time

print(f"题目 {fast_result['question_id']} - 快速模式评估结果:")
print(f"  知识点复杂度: {fast_result['knowledge_complexity']}/10")
print(f"  认知层级: {fast_result['cognitive_level']}/10")
print(f"  信息提取: {fast_result['info_extraction']}/10")
print(f"  推理复杂度: {fast_result['reasoning_steps']}/10")
print(f"  📊 最终难度: {fast_result['final_difficulty']}/10 ({fast_result['difficulty_label']})")
print(f"  ⏱️  预估答题时间: {fast_result['estimated_solve_time']}")
print(f"  🕒 评估耗时: {fast_time:.3f}秒")
print(f"  ✅ 模式: {fast_result['mode']}")
print(f"  🔧 LLM精调: {'是' if fast_result['refined'] else '否'}")

# 测试深度模式（无Gemini，会回退到快速模式）
print("\n【深度模式 🔬】（规则引擎 + LLM精调）")
print("-" * 80)
print("⚠️  注意: 未配置Gemini分析器，将自动回退到快速模式")
start_time = time.time()
deep_result = engine.evaluate_with_refinement(test_question, mode="deep")
deep_time = time.time() - start_time

print(f"题目 {deep_result['question_id']} - 深度模式评估结果:")
print(f"  📊 最终难度: {deep_result['final_difficulty']}/10 ({deep_result['difficulty_label']})")
print(f"  🕒 评估耗时: {deep_time:.3f}秒")
print(f"  ✅ 实际模式: {deep_result['mode']}")
print(f"  🔧 LLM精调: {'是' if deep_result['refined'] else '否'}")

print("\n" + "=" * 80)
print("📊 双模式对比总结")
print("=" * 80)
print(f"快速模式耗时: {fast_time:.3f}秒")
print(f"深度模式耗时: {deep_time:.3f}秒（当前无LLM，实际会慢~3秒）")
print(f"\n推荐使用场景:")
print(f"  🚄 快速模式: 试卷预览、批量分析、时间紧迫")
print(f"  🔬 深度模式: 正式报告、精确评估、质量优先")
print("=" * 80)
