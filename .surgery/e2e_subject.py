"""九学科报告管线 E2E：用指定 subject 跑分析+报告，验证学科 prompt 路由 + 动态素养维度 + 报告产出。
（用现有生物卷验证管线；内容错配不影响 prompt/维度/渲染管线验证）
运行：docker exec biology_backend python /app/e2e_subject.py <subject> <docx>
"""
import asyncio
import sys
import json
import pathlib
from deps import get_analysis_service
from subject_config import get_competency_dims, get_subject_name


async def main():
    subject = sys.argv[1] if len(sys.argv) > 1 else "chemistry"
    fn = sys.argv[2] if len(sys.argv) > 2 else "2025_hunan_gaokao_biology_scored_12.docx"
    path = f"/app/uploads/{fn}"
    with open(path, "rb") as f:
        data = f.read()

    svc = get_analysis_service()
    result = await svc.run_auto_analysis(
        file_path=path, filename=fn, file_bytes=data,
        mode="deep", subject=subject, generate_report=False,
    )
    qs = result.get("questions", [])
    competency_summary = result.get("competency_summary", {})
    exam_statistics = result.get("exam_statistics", {})
    analyzed_ok = sum(1 for q in qs if q.get("analysis") and not q.get("error"))

    # 报告：生产 router 路径
    from analysis_router import _generate_route_report_artifacts
    pdf_path = f"/app/reports/e2e_{subject}.pdf"
    await _generate_route_report_artifacts(
        qs, competency_summary, exam_statistics,
        {"name": fn, "total": len(qs), "mode": "deep", "subject": subject},
        "full", pathlib.Path(pdf_path),
    )

    expected = set(get_competency_dims(subject))
    # competency_summary 的维度键
    dist = competency_summary.get("distribution", competency_summary)
    summary_dims = set(k for k in (dist.keys() if isinstance(dist, dict) else []) if k in expected)
    html_path = pathlib.Path(pdf_path).with_suffix(".html")
    html = html_path.read_text(encoding="utf-8") if html_path.exists() else ""
    # 报告 HTML 含本学科维度名、不含其他学科特有维度
    dims_in_html = [d for d in expected if d in html]
    bio_only = {"生命观念", "社会责任"} - expected  # 生物专属（非生物时不应出现）
    bio_leak = [d for d in bio_only if d in html] if subject != "biology" else []

    print("==== E2E SUBJECT", subject, "(", get_subject_name(subject), ") ====")
    print("NUM_Q", len(qs), "ANALYZED_OK", f"{analyzed_ok}/{len(qs)}")
    print("expected_dims", sorted(expected))
    print("summary_has_dims", sorted(summary_dims))
    print("html_has_dims", sorted(dims_in_html))
    print("PDF_OK", pathlib.Path(pdf_path).exists() and pathlib.Path(pdf_path).stat().st_size > 1000)
    print("HTML_OK", html_path.exists())
    print("bio_dim_leak", bio_leak)
    ok = (analyzed_ok >= 1 and pathlib.Path(pdf_path).exists() and html_path.exists()
          and len(dims_in_html) >= max(1, len(expected) // 2) and not bio_leak)
    print("E2E_PASS" if ok else "E2E_FAIL")


asyncio.run(main())
