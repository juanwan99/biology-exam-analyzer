"""学科 Prompt 加载器 — 按学科加载对应的 prompt 模板文件。

设计文档: docs/plans/2026-03-28-multi-subject-design.md §2
"""
import os
from pathlib import Path
from logger import get_logger

logger = get_logger()

# 学科 prompts 目录：优先从环境变量读取，默认 BASE_DIR / "subject_prompts"
# Docker 中由 docker-compose 挂载 ./prompts -> /app/subject_prompts
_default_dir = Path(__file__).parent / "subject_prompts"
if not any(_default_dir.iterdir()) if _default_dir.exists() else True:
    _alt = Path(__file__).parent.parent / "prompts"
    if _alt.exists():
        _default_dir = _alt

_PROMPTS_DIR = Path(os.environ.get("SUBJECT_PROMPTS_DIR", str(_default_dir)))


class PromptLoader:
    """按学科加载 prompt 模板文件。

    优先加载学科专用 prompt，fallback 到 _base/ 目录。
    找不到任何文件时抛出 FileNotFoundError。
    """

    def __init__(self, subject: str = "biology"):
        self.subject = subject
        self.prompts_dir = _PROMPTS_DIR

    def load(self, prompt_name: str, **kwargs) -> str:
        """加载并渲染 prompt 模板。

        Args:
            prompt_name: 文件名（不含 .txt 后缀）
            **kwargs: 模板变量（逐个 str.replace 替换，兼容 JSON 花括号）

        Returns:
            渲染后的 prompt 字符串
        """
        subject_path = self.prompts_dir / self.subject / f"{prompt_name}.txt"
        base_path = self.prompts_dir / "_base" / f"{prompt_name}.txt"

        if subject_path.exists():
            path = subject_path
        elif base_path.exists():
            path = base_path
            logger.warning(f"[PromptLoader] {self.subject}/{prompt_name}.txt 不存在，使用 _base/ 版本")
        else:
            raise FileNotFoundError(
                f"Prompt 文件不存在: {subject_path} 和 {base_path} 均未找到")

        template = path.read_text(encoding="utf-8")

        if kwargs:
            # 使用逐个 str.replace 而非 str.format()，
            # 因为 prompt 模板含大量 JSON 花括号，format() 会误解析。
            result = template
            for key, value in kwargs.items():
                placeholder = "{" + key + "}"
                if placeholder not in result:
                    logger.warning(f"[PromptLoader] 模板变量 {{{key}}} 未在模板中出现, file={path}")
                result = result.replace(placeholder, str(value))
            return result
        return template

    def exists(self, prompt_name: str) -> bool:
        """检查 prompt 文件是否存在（学科专用或 _base）。"""
        subject_path = self.prompts_dir / self.subject / f"{prompt_name}.txt"
        base_path = self.prompts_dir / "_base" / f"{prompt_name}.txt"
        return subject_path.exists() or base_path.exists()
