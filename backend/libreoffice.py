"""LibreOffice 转 PDF。

每次转换用一个临时 profile（-env:UserInstallation），转完即删：
共用默认 profile 时，两份文件同时转换，第二个进程会撞上第一个的 profile 锁而失败（#48）。
"""
import os
import subprocess
import tempfile


def convert_to_pdf(src: str, out_dir: str, timeout: int) -> str:
    """把 src 转成 out_dir 下同名 .pdf，返回 pdf 路径；失败抛 RuntimeError，超时抛 subprocess.TimeoutExpired。"""
    with tempfile.TemporaryDirectory(prefix="lo_profile_") as profile:
        result = subprocess.run(
            ["soffice", f"-env:UserInstallation=file://{profile}", "--headless",
             "--convert-to", "pdf", "--outdir", out_dir, src],
            capture_output=True, text=True, timeout=timeout,
        )
    pdf_path = os.path.join(out_dir, os.path.splitext(os.path.basename(src))[0] + ".pdf")
    if result.returncode != 0 or not os.path.exists(pdf_path):
        raise RuntimeError(f"LibreOffice 转 PDF 失败（退出码 {result.returncode}）: {result.stderr[:200]}")
    return pdf_path
