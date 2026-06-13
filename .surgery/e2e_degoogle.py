"""degoogle E2E：真卷直连 pipeline（绕过 HTTP/auth），验证摘谷歌后分析+报告全链正常。
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
    result = await svc.run_auto_analysis(
        file_path=path, filename=fn, file_bytes=data,
        mode="deep", subject="biology",
        generate_report=True, report_mode="full",
        reports_dir="/app/reports", exam_id="degoogle_e2e_20260613",
    )
    dt = time.time() - t0

    qs = result.get("questions", [])
    analyzed_ok = sum(1 for q in qs if q.get("analysis") and not q.get("error"))
    insights = result.get("report_insights") or {}
    insights_str = json.dumps(insights, ensure_ascii=False, default=str)

    print("==== E2E RESULT ====")
    print("ELAPSED_MIN", round(dt / 60, 1))
    print("NUM_Q", len(qs))
    print("ANALYZED_OK", f"{analyzed_ok}/{len(qs)}")
    print("REPORT_PDF", result.get("report_url"))
    print("REPORT_HTML", result.get("html_report_url"))
    print("REPORT_ERROR", result.get("report_error"))
    # degoogle 断言：这些 key 必须全部消失
    print("HAS_channel_usage", "channel_usage" in result)
    print("HAS__grounding_status", "_grounding_status" in insights_str)
    print("HAS__grounding_checks", "_grounding_checks" in insights_str)
    print("HAS_stabilized_for_grounding", "_stabilized_for_grounding" in insights_str)
    # 通过判定
    ok = (
        analyzed_ok >= max(1, int(len(qs) * 0.9))
        and result.get("report_url")
        and result.get("html_report_url")
        and not result.get("report_error")
        and "channel_usage" not in result
        and "_grounding_status" not in insights_str
        and "_grounding_checks" not in insights_str
    )
    print("E2E_PASS" if ok else "E2E_FAIL")


asyncio.run(main())
