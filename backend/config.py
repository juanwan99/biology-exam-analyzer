"""
路径配置模块
支持 Docker 环境和本地开发环境
"""
import os
from pathlib import Path

# 基础路径（支持环境变量覆盖）
BASE_DIR = Path(os.environ.get("APP_BASE_DIR", os.path.dirname(__file__)))

# 各个子目录
UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", BASE_DIR / "uploads"))
LOG_DIR = Path(os.environ.get("LOG_DIR", BASE_DIR / "logs"))
PROMPT_DIR = Path(os.environ.get("PROMPT_DIR", BASE_DIR / "prompts"))
RULES_DIR = Path(os.environ.get("RULES_DIR", BASE_DIR / "rules"))
REPORTS_DIR = Path(os.environ.get("REPORTS_DIR", BASE_DIR / "reports"))

# 确保目录存在
for directory in [UPLOAD_DIR, LOG_DIR, PROMPT_DIR, RULES_DIR, REPORTS_DIR]:
    directory.mkdir(parents=True, exist_ok=True)
