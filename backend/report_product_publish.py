"""Publish report artifacts from the shared report aggregate."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

try:
    from weasyprint import HTML
except ModuleNotFoundError:  # pragma: no cover - exercised when PDF support is not installed.
    HTML = None

from report_product_html import render_report_product_pdf_html, write_report_product_html
from report_product_model import build_report_product_model


def write_report_artifacts(
    report_data: Dict[str, Any],
    insights: Dict[str, Any],
    mode: str = "full",
    pdf_path: str | Path | None = None,
) -> Dict[str, str | None]:
    """Write commercial PDF and web HTML reports from one product model."""
    output_path = str(pdf_path) if pdf_path else None
    product_model = build_report_product_model(report_data, insights)

    if pdf_path:
        if HTML is None:
            raise RuntimeError("weasyprint is required to write PDF report artifacts")
        pdf_target = Path(pdf_path)
        pdf_target.parent.mkdir(parents=True, exist_ok=True)
        HTML(
            string=render_report_product_pdf_html(product_model),
            base_url=str(pdf_target.parent),
        ).write_pdf(str(pdf_target))

    html_path = None
    if pdf_path:
        html_path = Path(pdf_path).with_suffix(".html")
        write_report_product_html(product_model, html_path)

    return {
        "pdf_path": output_path,
        "html_path": str(html_path) if html_path else None,
    }
