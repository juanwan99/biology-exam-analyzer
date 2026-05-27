import os
import pytest

__test__ = False

pytestmark = pytest.mark.skipif(
    not os.environ.get("DEEPSEEK_API_KEY"),
    reason="需要 DEEPSEEK_API_KEY 环境变量（集成测试）"
)

"""9学科端到端验证脚本 — 每科 1 选择题 + 1 大题，共 18 道。

直接调用 DifficultyPipeline，跳过 API/认证层。
"""
import asyncio
import sys
import time
import traceback

from difficulty_pipeline import DifficultyPipeline
from prompt_loader import PromptLoader

# ========== 9 学科测试用例（每科 2 道） ==========

QUESTIONS = {
    # ===== 生物 =====
    "biology_choice": {
        "content": "下列关于细胞膜的叙述，错误的是\nA. 细胞膜主要由脂质和蛋白质组成\nB. 不同功能的细胞，其细胞膜上蛋白质的种类和数量相同\nC. 细胞膜具有一定的流动性\nD. 细胞膜具有选择透过性",
        "question_type": "选择题", "correct_answer": "B", "total_score": 2, "subject": "biology",
    },
    "biology_big": {
        "content": "某实验小组为验证生长素的极性运输，设计了如下实验：取甲、乙两组形态大小相同的琼脂块，甲组含适宜浓度的生长素，乙组不含。再取若干去尖端的胚芽鞘段，实验操作和结果如图所示。\n(1) 该实验的自变量是什么？（2分）\n(2) 琼脂块A和B中，哪个含有生长素？为什么？（4分）\n(3) 如果将胚芽鞘倒置放置，预期结果会怎样？说明理由。（4分）",
        "question_type": "实验题", "correct_answer": "见解析", "total_score": 10, "subject": "biology",
    },

    # ===== 化学 =====
    "chemistry_choice": {
        "content": "下列离子方程式正确的是\nA. 铁与稀硫酸反应：2Fe + 6H\u207a \u2192 2Fe\u00b3\u207a + 3H\u2082\u2191\nB. 碳酸钙与盐酸反应：CO\u2083\u00b2\u207b + 2H\u207a \u2192 H\u2082O + CO\u2082\u2191\nC. 氢氧化钡与稀硫酸反应：Ba\u00b2\u207a + 2OH\u207b + 2H\u207a + SO\u2084\u00b2\u207b \u2192 BaSO\u2084\u2193 + 2H\u2082O\nD. 铜与硝酸银溶液反应：Cu + Ag\u207a \u2192 Cu\u00b2\u207a + Ag",
        "question_type": "选择题", "correct_answer": "C", "total_score": 3, "subject": "chemistry",
    },
    "chemistry_big": {
        "content": "工业上用铝土矿（主要成分Al\u2082O\u2083，含SiO\u2082、Fe\u2082O\u2083杂质）提取氧化铝的工艺流程如下：铝土矿\u2192加NaOH溶液溶解\u2192过滤（残渣1）\u2192通入过量CO\u2082\u2192过滤（残渣2）\u2192灼烧\u2192Al\u2082O\u2083\n(1) 写出Al\u2082O\u2083与NaOH反应的化学方程式。（2分）\n(2) 残渣1的主要成分是什么？（2分）\n(3) 通入过量CO\u2082的目的是什么？写出反应方程式。（4分）\n(4) 该流程能否用盐酸代替NaOH？说明理由。（4分）",
        "question_type": "工艺流程题", "correct_answer": "见解析", "total_score": 12, "subject": "chemistry",
    },

    # ===== 语文 =====
    "chinese_choice": {
        "content": "下列各句中加点成语的使用，全都正确的一项是\nA. 这部小说情节曲折，抑扬顿挫，读来引人入胜。\nB. 他的演讲深入浅出，听众无不侧目而视，深受启发。\nC. 经过艰苦训练，他的书法终于登堂入室，作品多次获奖。\nD. 面对突如其来的灾难，人们不知所措，乱作一团。",
        "question_type": "选择题", "correct_answer": "C", "total_score": 3, "subject": "chinese",
    },
    "chinese_big": {
        "content": "阅读下面的文字，完成(1)-(3)题。\n故乡的野菜（周作人）\n我的故乡不止一个，凡我住过的地方都是故乡。故乡对于我并没有什么特别的情分，只因钓于斯游于斯的关系，朝夕会面，遂成相识，正如乡村里的邻舍一样，虽然不是亲属，别后有时也要想念到他。\n(1) 文中\"故乡对于我并没有什么特别的情分\"是否意味着作者对故乡毫无感情？结合全文分析。（4分）\n(2) 赏析文中画线句子的表达效果。（4分）\n(3) 本文语言风格有何特点？试举例分析。（6分）",
        "question_type": "现代文阅读", "correct_answer": "见解析", "total_score": 14, "subject": "chinese",
    },

    # ===== 数学 =====
    "math_choice": {
        "content": "已知集合A={x|x\u00b2-3x+2=0}，B={x|x\u00b2-ax+a-1=0}，若B\u2286A，则实数a的取值集合为\nA. {2}\nB. {3}\nC. {2,3}\nD. {1,2,3}",
        "question_type": "选择题", "correct_answer": "C", "total_score": 5, "subject": "math",
    },
    "math_big": {
        "content": "已知函数f(x)=x\u00b3-3ax\u00b2+3x+1，其中a为常数。\n(1) 当a=1时，求f(x)的单调递减区间。（4分）\n(2) 若f(x)在区间(0,1)上单调递增，求a的取值范围。（4分）\n(3) 当a>0时，讨论f(x)的极值。（6分）",
        "question_type": "解答题", "correct_answer": "见解析", "total_score": 14, "subject": "math",
    },

    # ===== 英语 =====
    "english_choice": {
        "content": "The teacher demanded that every student ______ the exam on time.\nA. finishes\nB. finished\nC. finish\nD. would finish",
        "question_type": "选择题", "correct_answer": "C", "total_score": 1, "subject": "english",
    },
    "english_big": {
        "content": "阅读理解：\nPassage: Scientists have found that trees communicate with each other through an underground network of fungi. This 'Wood Wide Web' allows trees to share nutrients and send warning signals about insect attacks. Research shows that mother trees nurture their seedlings by sending them carbon through the fungal network.\n(1) What is the 'Wood Wide Web'? (2 marks)\n(2) How do mother trees help their seedlings according to the passage? (2 marks)\n(3) What can we infer about the relationship between trees in a forest? (4 marks)",
        "question_type": "阅读理解", "correct_answer": "见解析", "total_score": 8, "subject": "english",
    },

    # ===== 物理 =====
    "physics_choice": {
        "content": "一个物体从高处自由下落（不计空气阻力，g取10m/s\u00b2），经过2s到达地面，则物体下落的高度和着地速度分别为\nA. 10m，10m/s\nB. 20m，20m/s\nC. 20m，10m/s\nD. 40m，20m/s",
        "question_type": "选择题", "correct_answer": "B", "total_score": 4, "subject": "physics",
    },
    "physics_big": {
        "content": "如图所示，质量m=2kg的物体置于倾角\u03b8=30\u00b0的粗糙斜面上，在沿斜面向上的力F=20N作用下，沿斜面匀速上滑。g取10m/s\u00b2。\n(1) 对物体进行受力分析，画出力的示意图。（2分）\n(2) 求斜面对物体的支持力N。（3分）\n(3) 求物体与斜面间的动摩擦因数\u03bc。（5分）",
        "question_type": "计算题", "correct_answer": "见解析", "total_score": 10, "subject": "physics",
    },

    # ===== 历史 =====
    "history_choice": {
        "content": "1954年，中华人民共和国第一届全国人民代表大会召开，其最重要的成果是\nA. 通过了《共同纲领》\nB. 制定了《中华人民共和国宪法》\nC. 提出了和平共处五项原则\nD. 完成了三大改造",
        "question_type": "选择题", "correct_answer": "B", "total_score": 4, "subject": "history",
    },
    "history_big": {
        "content": "材料一：中国古代选官制度经历了从世袭制到察举制再到科举制的演变。\n材料二：科举制度自隋唐创立以来，延续了一千三百多年，对中国社会产生了深远影响。\n(1) 简述察举制与科举制的主要区别。（4分）\n(2) 结合所学知识，分析科举制的积极影响和局限性。（6分）\n(3) 科举制对现代人才选拔制度有何借鉴意义？（4分）",
        "question_type": "材料分析题", "correct_answer": "见解析", "total_score": 14, "subject": "history",
    },

    # ===== 地理 =====
    "geography_choice": {
        "content": "下列关于地球自转的叙述，正确的是\nA. 地球自转的周期为24小时，即一个恒星日\nB. 地球自转线速度从赤道向两极递减\nC. 地球自转产生了四季更替\nD. 地球自转方向为自东向西",
        "question_type": "选择题", "correct_answer": "B", "total_score": 4, "subject": "geography",
    },
    "geography_big": {
        "content": "阅读图文材料，完成下列要求。\n材料：某地位于我国东南沿海，年降水量1200mm以上，夏季高温多雨，冬季温和少雨。该地近年来大力发展茶叶种植业。\n(1) 判断该地的气候类型，并说明依据。（4分）\n(2) 分析该地发展茶叶种植的有利自然条件。（4分）\n(3) 为促进该地茶产业可持续发展，请提出合理建议。（6分）",
        "question_type": "综合题", "correct_answer": "见解析", "total_score": 14, "subject": "geography",
    },

    # ===== 政治 =====
    "politics_choice": {
        "content": "在我国，人民行使国家权力的机关是\nA. 中国共产党各级委员会\nB. 各级人民代表大会\nC. 各级人民政府\nD. 各级人民法院和人民检察院",
        "question_type": "选择题", "correct_answer": "B", "total_score": 4, "subject": "politics",
    },
    "politics_big": {
        "content": "材料：某市政府为解决老旧小区停车难问题，通过网上问卷调查、召开居民座谈会、邀请专家论证等方式广泛征求意见，最终出台了《老旧小区停车管理办法》。\n(1) 结合材料，说明该市政府决策过程体现了哪些民主决策方式？（4分）\n(2) 运用政治生活知识，分析该市政府为什么要广泛征求意见。（4分）\n(3) 作为公民，你还可以通过哪些途径参与民主决策？（4分）",
        "question_type": "材料分析题", "correct_answer": "见解析", "total_score": 12, "subject": "politics",
    },
}

# 9 学科列表
SUBJECTS = ["biology", "chemistry", "chinese", "math", "english",
            "physics", "history", "geography", "politics"]


async def test_question(name: str, question: dict, pipeline: DifficultyPipeline) -> dict:
    """测试单道题目，返回结果 dict。"""
    subject = question["subject"]
    qtype = "choice" if "choice" in name else "big"
    print(f"\n{'='*70}")
    print(f"[{name}]  subject={subject}  type={question['question_type']}  score={question['total_score']}")
    print(f"题目前80字: {question['content'][:80]}...")
    print(f"{'='*70}")

    # 1. 验证 PromptLoader
    loader = PromptLoader(subject)
    prompt_ok = loader.exists("feature_extractor")
    if not prompt_ok:
        print(f"  WARNING: {subject}/feature_extractor.txt 不存在，将 fallback 到 _base/")
    else:
        print(f"  Prompt: {subject}/feature_extractor.txt OK")

    # 2. 调用 pipeline
    t0 = time.time()
    try:
        result = await pipeline.evaluate_with_refinement(question)
        elapsed = time.time() - t0

        difficulty = result.get("final_difficulty", -1)
        label = result.get("difficulty_label", "N/A")
        confidence = result.get("confidence", -1)
        flags = result.get("flags", [])

        print(f"\n  Result ({elapsed:.1f}s):")
        print(f"    difficulty: {difficulty}")
        print(f"    label:      {label}")
        print(f"    confidence: {confidence}")
        print(f"    flags:      {flags}")

        features = result.get("features", {})
        key_features = {}
        for k in ["working_memory", "reasoning_steps", "chain_coupling",
                   "trap_density", "novelty", "knowledge_breadth"]:
            v = features.get(k)
            if v is not None:
                key_features[k] = v
                print(f"    {k}: {v}")

        # 大题额外信息
        bq = features.get("_big_question")
        if bq:
            n_sub = len(bq.get("subquestions", []))
            n_dep = len(bq.get("dependencies", []))
            eff = bq.get("effective_steps", "?")
            print(f"    [big] subquestions={n_sub}, dependencies={n_dep}, effective_steps={eff}")

        return {
            "name": name,
            "subject": subject,
            "qtype": qtype,
            "ok": True,
            "difficulty": difficulty,
            "label": label,
            "confidence": confidence,
            "elapsed": elapsed,
            "key_features": key_features,
            "error": None,
        }
    except Exception as e:
        elapsed = time.time() - t0
        print(f"  ERROR ({elapsed:.1f}s): {e}")
        traceback.print_exc()
        return {
            "name": name,
            "subject": subject,
            "qtype": qtype,
            "ok": False,
            "difficulty": -1,
            "label": "ERROR",
            "confidence": -1,
            "elapsed": elapsed,
            "key_features": {},
            "error": str(e),
        }


async def main():
    print("=" * 70)
    print("  9-Subject End-to-End Test (18 questions)")
    print("  Subjects:", ", ".join(SUBJECTS))
    print("=" * 70)

    pipeline = DifficultyPipeline()
    results = []
    t_start = time.time()

    # Process questions in order: for each subject, choice then big
    for subj in SUBJECTS:
        choice_key = f"{subj}_choice"
        big_key = f"{subj}_big"
        for key in [choice_key, big_key]:
            if key in QUESTIONS:
                r = await test_question(key, QUESTIONS[key], pipeline)
                results.append(r)
            else:
                print(f"\n  WARNING: test case '{key}' not found, skipping")

    t_total = time.time() - t_start

    # ========== Summary Table ==========
    print("\n")
    print("=" * 100)
    print("  SUMMARY TABLE  —  9 Subjects x 2 Questions = 18 Total")
    print("=" * 100)
    header = f"{'#':>2}  {'Subject':<12} {'Type':<8} {'Status':<6} {'Diff':>5} {'Label':<12} {'Conf':>5} {'Time':>6}  Key Features"
    print(header)
    print("-" * 100)

    pass_count = 0
    fail_count = 0
    for i, r in enumerate(results, 1):
        status = "OK" if r["ok"] else "FAIL"
        if r["ok"]:
            pass_count += 1
        else:
            fail_count += 1

        feat_str = ", ".join(f"{k}={v}" for k, v in r["key_features"].items()) if r["key_features"] else "-"
        if len(feat_str) > 50:
            feat_str = feat_str[:47] + "..."

        print(f"{i:>2}  {r['subject']:<12} {r['qtype']:<8} {status:<6} "
              f"{r['difficulty']:>5.1f} {r['label']:<12} {r['confidence']:>5.2f} "
              f"{r['elapsed']:>5.1f}s  {feat_str}")

    print("-" * 100)
    print(f"Total: {pass_count} OK / {fail_count} FAIL / {len(results)} total  |  "
          f"Elapsed: {t_total:.1f}s")

    # ========== Per-Subject Summary ==========
    print("\n")
    print("=" * 70)
    print("  PER-SUBJECT STATUS")
    print("=" * 70)
    for subj in SUBJECTS:
        subj_results = [r for r in results if r["subject"] == subj]
        all_ok = all(r["ok"] for r in subj_results)
        status_icon = "PASS" if all_ok else "FAIL"
        details = []
        for r in subj_results:
            if r["ok"]:
                details.append(f"{r['qtype']}={r['label']}({r['difficulty']:.1f})")
            else:
                details.append(f"{r['qtype']}=ERROR({r['error'][:30] if r['error'] else '?'})")
        print(f"  [{status_icon}] {subj:<12}  {' | '.join(details)}")

    print("=" * 70)

    # ========== Error Details ==========
    errors = [r for r in results if not r["ok"]]
    if errors:
        print("\n  ERRORS:")
        for r in errors:
            print(f"    - {r['name']}: {r['error']}")

    sys.exit(0 if fail_count == 0 else 1)


if __name__ == "__main__":
    asyncio.run(main())
