"""后台任务状态管理 — 为 B4 SSE 进度做准备。

内存级 dict + TTL 清理。单机够用，进程重启丢失可接受。
"""
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TaskStatus:
    stage: str = "pending"
    percent: int = 0
    message: str = ""
    result: Any = None
    created_at: float = field(default_factory=time.time)


_tasks: dict[str, TaskStatus] = {}
_TTL = 30 * 60  # 30 分钟


def create_task(task_id: str) -> TaskStatus:
    _cleanup()
    status = TaskStatus()
    _tasks[task_id] = status
    return status


def update_task(task_id: str, stage: str, percent: int, message: str = ""):
    if task_id in _tasks:
        t = _tasks[task_id]
        t.stage = stage
        t.percent = percent
        t.message = message


def get_task(task_id: str) -> TaskStatus | None:
    return _tasks.get(task_id)


def set_result(task_id: str, result: Any):
    if task_id in _tasks:
        _tasks[task_id].result = result
        _tasks[task_id].stage = "done"
        _tasks[task_id].percent = 100


def set_error(task_id: str, error: str):
    if task_id in _tasks:
        _tasks[task_id].stage = "error"
        _tasks[task_id].message = error


def _cleanup():
    now = time.time()
    expired = [k for k, v in _tasks.items() if now - v.created_at > _TTL]
    for k in expired:
        del _tasks[k]
