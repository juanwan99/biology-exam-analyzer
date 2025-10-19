import logging
from datetime import datetime
import os

# 创建日志目录
os.makedirs("/app/logs", exist_ok=True)

# 配置日志
logger = logging.getLogger("biology_analyzer")
logger.setLevel(logging.DEBUG)

# 文件处理器（详细日志）
file_handler = logging.FileHandler(
    f"/app/logs/{datetime.now().strftime('%Y%m%d')}.log",
    encoding='utf-8'
)
file_handler.setLevel(logging.DEBUG)
file_formatter = logging.Formatter(
    '[%(asctime)s] %(levelname)s - %(funcName)s:%(lineno)d - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
file_handler.setFormatter(file_formatter)

# 控制台处理器（关键信息）
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_formatter = logging.Formatter(
    '[%(levelname)s] %(message)s'
)
console_handler.setFormatter(console_formatter)

logger.addHandler(file_handler)
logger.addHandler(console_handler)

def get_logger():
    return logger
