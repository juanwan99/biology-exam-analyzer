"""degoogle E2E：真卷直连，精确镜像生产 analyze_auto 报告路径（_generate_route_report_artifacts，
无 assert_pipeline_ready 硬门，与用户实际路径一致）。验证摘谷歌后分析+报告全链产出真 PDF/HTML。
运行：docker exec biology_backend python /app/e2e_degoogle.py <docx文件名>
"""
import asyncio
import time
import sys
import json
from deps import get_analysis_service


async def main():
    fn = sys.argv[1] if len(sys.argv) > 1 else "2025_hunan_gaokao_biology_scored_12.docx"
    path = f"/app/uploads/{fn}"
    with open(path, "rb") as f:
        data = f.read()

    svc = get_analysis_service()
    t0 = time.time()
    # 1) 分析（不在此处生成报告，避开 run_auto_analysis 的严格 assert_pipeline_ready 门，
    #    与生产 analyze_auto 一致：生产报告走 router._generate_route_report_artifacts）
    result = await svc.run_auto_analysis(
        file_path=path, filename=fn, file_bytes=data,
        mode="deep", subject="biology", generate_report=False,
    )
    t_analyze = time.time() - t0

    qs = result.get("questions", [])
    competency_summary = result.get("competency_summary", {})
    exam_statistics = result.get("exam_statistics", {})
    analyzed_ok = sum(1 for q in qs if q.get("analysis") and not q.get("error"))

    # 2) 报告：精确复用生产 router 路径
    from analysis_router import _generate_route_report_artifacts
    import os
    os.makedirs("/app/reports", exist_ok=True)
    pdf_path = "/app/reports/degoogle_e2e_prod.pdf"
    t1 = time.time()
    artifacts = await _generate_route_report_artifacts(
        qs, competency_summary, exam_statistics,
        {"name": fn, "total": len(qs), "mode": "deep"},
        "full", __import__("pathlib").Path(pdf_path),
    )
    t_report = time.time() - t1

    insights = svc._last_report_insights or {}
    insights_str = json.dumps(insights, ensure_ascii=False, default=str)
    import pathlib
    pdf_ok = pathlib.Path(pdf_path).exists() and pathlib.Path(pdf_path).stat().st_size > 1000
    html_ok = pathlib.Path(pdf_path).with_suffix(".html").exists()

    print("==== E2E RESULT (生产路径) ====")
    print("ANALYZE_MIN", round(t_analyze / 60, 1))
    print("REPORT_MIN", round(t_report / 60, 1))
    print("NUM_Q", len(qs))
    print("ANALYZED_OK", f"{analyzed_ok}/{len(qs)}")
    print("PDF_OK", pdf_ok)
    print("HTML_OK", html_ok)
    print("ARTIFACTS", artifacts)
    # degoogle 断言：grounding key 必须全消失
    print("HAS__grounding_status", "_grounding_status" in insights_str)
    print("HAS__grounding_checks", "_grounding_checks" in insights_str)
    print("HAS_stabilized_for_grounding", "_stabilized_for_grounding" in insights_str)
    print("INSIGHTS_LLM_CALLS", len(insights.get("_llm_calls", [])))
    ok = (
        analyzed_ok >= max(1, int(len(qs) * 0.9))
        and pdf_ok and html_ok
        and "_grounding_status" not in insights_str
        and "_grounding_checks" not in insights_str
        and "_stabilized_for_grounding" not in insights_str
    )
    print("E2E_PASS" if ok else "E2E_FAIL")


asyncio.run(main())
