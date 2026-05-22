import pytest
from fastapi import HTTPException

import admin_router


@pytest.mark.asyncio
async def test_download_report_serves_html_inline(monkeypatch, tmp_path):
    report_path = tmp_path / "exam.html"
    report_path.write_text("<html>report</html>", encoding="utf-8")
    monkeypatch.setattr(admin_router, "REPORTS_DIR", tmp_path)

    response = await admin_router.download_report("exam.html")

    assert response.media_type == "text/html; charset=utf-8"
    assert "attachment" not in response.headers.get("content-disposition", "").lower()
    assert response.headers["x-content-type-options"] == "nosniff"


@pytest.mark.asyncio
async def test_download_report_rejects_unknown_report_type(monkeypatch, tmp_path):
    report_path = tmp_path / "exam.txt"
    report_path.write_text("secret", encoding="utf-8")
    monkeypatch.setattr(admin_router, "REPORTS_DIR", tmp_path)

    with pytest.raises(HTTPException) as exc_info:
        await admin_router.download_report("exam.txt")

    assert exc_info.value.status_code == 400
