"""LibreOffice 转 PDF：每次转换独立 profile，同时转两份不互撞（#48）。"""
import subprocess
from pathlib import Path

import pytest

from libreoffice import convert_to_pdf


def _fake_run(calls, ok=True):
    def run(cmd, **kwargs):
        profile = next(a for a in cmd if a.startswith("-env:UserInstallation=file://"))
        calls.append((cmd, Path(profile.removeprefix("-env:UserInstallation=file://")).exists()))
        if ok:
            outdir = cmd[cmd.index("--outdir") + 1]
            Path(outdir, Path(cmd[-1]).stem + ".pdf").write_bytes(b"%PDF-1.4 fake")
        return subprocess.CompletedProcess(cmd, 0 if ok else 1, "", "" if ok else "boom")
    return run


def test_each_conversion_gets_its_own_profile(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr("libreoffice.subprocess.run", _fake_run(calls))
    assert convert_to_pdf(str(tmp_path / "a.docx"), str(tmp_path), 60) == str(tmp_path / "a.pdf")
    assert convert_to_pdf(str(tmp_path / "b.docx"), str(tmp_path), 60) == str(tmp_path / "b.pdf")
    profiles = [next(a for a in cmd if a.startswith("-env:")) for cmd, _ in calls]
    assert profiles[0] != profiles[1]
    assert all(existed for _, existed in calls)  # 转换时 profile 目录在
    assert not any(Path(p.removeprefix("-env:UserInstallation=file://")).exists() for p in profiles)  # 转完删掉


def test_failure_raises(monkeypatch, tmp_path):
    monkeypatch.setattr("libreoffice.subprocess.run", _fake_run([], ok=False))
    with pytest.raises(RuntimeError, match="boom"):
        convert_to_pdf(str(tmp_path / "a.docx"), str(tmp_path), 60)
