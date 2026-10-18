"""Analysis task manager — SQLite via runtime_store, same public API."""
import uuid
from datetime import datetime
from logger import get_logger
import runtime_store

logger = get_logger()


def create(total_questions: int) -> str:
    task_id = uuid.uuid4().hex[:8]
    runtime_store.put_task(task_id, {
        "status": "processing",
        "progress": 0,
        "total": total_questions,
        "message": "开始分析...",
        "result": None,
        "error": None,
        "created_at": datetime.now().isoformat(),
    })
    logger.info("[任务] 创建任务 %s，共 %s 题", task_id, total_questions)
    return task_id


def update(task_id: str, progress: int, message: str = None):
    row = runtime_store.get_task(task_id)
    if not row:
        return
    row["progress"] = progress
    if message:
        row["message"] = message
    runtime_store.put_task(task_id, row)


def complete(task_id: str, result: dict):
    row = runtime_store.get_task(task_id) or {}
    row["status"] = "completed"
    row["result"] = result
    row["message"] = "分析完成"
    runtime_store.put_task(task_id, row)
    logger.info("[任务] 任务 %s 完成", task_id)


def fail(task_id: str, error: str):
    row = runtime_store.get_task(task_id) or {}
    row["status"] = "failed"
    row["error"] = error
    row["message"] = "分析失败: %s" % error
    runtime_store.put_task(task_id, row)
    logger.error("[任务] 任务 %s 失败: %s", task_id, error)


def get(task_id: str):
    return runtime_store.get_task(task_id)


def cleanup(max_age_hours: int = 2):
    n = runtime_store.cleanup_tasks(max_age_hours)
    if n:
        logger.info("[任务] 清理 %s 个过期任务", n)
