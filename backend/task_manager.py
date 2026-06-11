"""In-memory async task manager for long-running analysis jobs."""
import uuid
from datetime import datetime
from logger import get_logger

logger = get_logger()

_tasks = {}


def create(total_questions: int) -> str:
    task_id = uuid.uuid4().hex[:8]
    _tasks[task_id] = {
        "status": "processing",
        "progress": 0,
        "total": total_questions,
        "message": "开始分析...",
        "result": None,
        "error": None,
        "created_at": datetime.now().isoformat(),
    }
    logger.info(f"[任务] 创建任务 {task_id}，共 {total_questions} 题")
    return task_id


def update(task_id: str, progress: int, message: str = None):
    if task_id in _tasks:
        _tasks[task_id]["progress"] = progress
        if message:
            _tasks[task_id]["message"] = message


def complete(task_id: str, result: dict):
    if task_id in _tasks:
        _tasks[task_id]["status"] = "completed"
        _tasks[task_id]["result"] = result
        _tasks[task_id]["message"] = "分析完成"
        logger.info(f"[任务] 任务 {task_id} 完成")


def fail(task_id: str, error: str):
    if task_id in _tasks:
        _tasks[task_id]["status"] = "failed"
        _tasks[task_id]["error"] = error
        _tasks[task_id]["message"] = f"分析失败: {error}"
        logger.error(f"[任务] 任务 {task_id} 失败: {error}")


def get(task_id: str) -> dict | None:
    return _tasks.get(task_id)


def cleanup(max_age_hours: int = 2):
    now = datetime.now()
    expired = [
        tid for tid, t in _tasks.items()
        if (now - datetime.fromisoformat(t["created_at"])).total_seconds() > max_age_hours * 3600
    ]
    for tid in expired:
        del _tasks[tid]
    if expired:
        logger.info(f"[任务] 清理 {len(expired)} 个过期任务")
