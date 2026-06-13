"""每科真卷端到端 E2E：用 test_9subjects 各科真题（choice+big，2题/科），
跑全管线 analyze→competency→report，验证拆题/分析/报告 PDF+HTML + 素养维度符合该科课标。
对应 GOAL 目标2 验收"9科每科≥1份真实试卷端到端跑通"。
运行：docker exec biology_backend python /app/per_subject_e2e.py [subject1 subject2 ...]
"""
import asyncio
import sys
import pathlib
from deps import get_analysis_service, get_competency_analyzer
from analysis_statistics import generate_exam_statistics, _build_competency_list
from analysis_router import _generate_route_report_artifacts
from subject_config import get_competency_dims, get_subject_name
from test_9subjects import QUESTIONS

ALL = ["chinese", "math", "english", "physics", "chemistry",
       "biology", "politics", "history", "geography"]


async def run_subject(svc, ca, subject):
    # 该科真题（选择+大题）
    qs = []
    for suffix in ("choice", "big"):
        q = dict(QUESTIONS[f"{subject}_choice"] if suffix == "choice" else QUESTIONS[f"{subject}_big"])
        q["id"] = len(qs) + 1
        q["subject"] = subject
        qs.append(q)

    analyzed = await svc.analyze_questions_batch(qs, [], "deep", subject)
    analyzed_ok = sum(1 for q in analyzed if q.get("analysis") and not q.get("error"))
    competency_list = _build_competency_list(analyzed)
    competency_summary = ca.aggregate_exam_competencies(competency_list, subject)
    exam_statistics = generate_exam_statistics(analyzed, competency_summary)

    pdf_path = pathlib.Path(f"/app/reports/persubj_{subject}.pdf")
    await _generate_route_report_artifacts(
        analyzed, competency_summary, exam_statistics,
        {"name": f"{get_subject_name(subject)}测试卷", "total": len(analyzed), "mode": "deep", "subject": subject},
        "full", pdf_path,
    )
    html_path = pdf_path.with_suffix(".html")
    html = html_path.read_text(encoding="utf-8") if html_path.exists() else ""
    expected = set(get_competency_dims(subject))
    dims_in_html = [d for d in expected if d in html]
    # 真维度泄漏检测：报告实际聚合的核心素养维度（competency_summary 各顶层 distribution 的 keys）应 ⊆ 本科 expected。
    # 不在 HTML 全文做子串匹配——其他科顶层维度名会作为知识点（如生物采分点"实验结果的逻辑推理"）、
    # 子能力细分（英语"思维品质"含"逻辑推理"、政治"公共参与"含"社会责任"）、LLM 散文大量合理出现，全文子串必然误报。
    # aggregate_exam_competencies 的各 distribution 用 {comp:0 for comp in 本科维度} 初始化，顶层 keys 即核心素养维度。
    _cs = competency_summary if isinstance(competency_summary, dict) else {}
    _actual_dims = set()
    for _k in ("primary_distribution", "involved_distribution", "distribution", "seu_primary_distribution"):
        _actual_dims |= set((_cs.get(_k) or {}).keys())
    leak = sorted(_actual_dims - expected)

    pdf_ok = pdf_path.exists() and pdf_path.stat().st_size > 1000
    ok = (analyzed_ok == len(qs) and pdf_ok and html_path.exists()
          and len(dims_in_html) >= max(1, len(expected) - 1) and not leak)
    print(f"{'PASS' if ok else 'FAIL'} {subject:9s}({get_subject_name(subject)}) "
          f"analyzed={analyzed_ok}/{len(qs)} pdf={pdf_ok} html={html_path.exists()} "
          f"dims_in_html={len(dims_in_html)}/{len(expected)} leak={leak}")
    return ok


async def main():
    subjects = sys.argv[1:] or ALL
    svc, ca = get_analysis_service(), get_competency_analyzer()
    results = []
    for s in subjects:
        try:
            results.append(await run_subject(svc, ca, s))
        except Exception as e:
            import traceback
            print(f"FAIL {s:9s} EXCEPTION {type(e).__name__}: {str(e)[:100]}")
            traceback.print_exc()
            results.append(False)
    print(f"==== 每科真卷 E2E {sum(results)}/{len(subjects)} {'ALL PASS' if sum(results)==len(subjects) else 'SOME FAIL'} ====")


asyncio.run(main())
