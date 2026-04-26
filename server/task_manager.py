import threading
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from server.log_buffer import LogBuffer


@dataclass
class ManagedTask:
    task_id: str
    status: str = "pending"
    summary: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    thread: Optional[threading.Thread] = None


class TaskManager:
    def __init__(self, log_buffer: Optional[LogBuffer] = None):
        self.log_buffer = log_buffer or LogBuffer()
        self.tasks: dict[str, ManagedTask] = {}
        self._lock = threading.Lock()

    def create_task(self) -> ManagedTask:
        task = ManagedTask(task_id=str(uuid.uuid4()))
        with self._lock:
            self.tasks[task.task_id] = task
        return task

    def append_log(self, task_id: str, line: str):
        self.log_buffer.append(task_id, line)

    def get_logs(self, task_id: str) -> list[str]:
        return self.log_buffer.get(task_id)

    def get_task(self, task_id: str) -> Optional[ManagedTask]:
        return self.tasks.get(task_id)

    def list_tasks(self) -> list[ManagedTask]:
        return list(self.tasks.values())

    def run_background(self, target: Callable[..., Any], *, task: ManagedTask, args: tuple = (), kwargs: Optional[dict] = None):
        kwargs = kwargs or {}

        def runner():
            task.status = "running"
            try:
                result = target(*args, **kwargs)
                if isinstance(result, dict):
                    task.summary = result
                task.status = "success"
            except Exception as exc:
                task.error = str(exc)
                task.status = "failed"
                self.append_log(task.task_id, f"[ERROR] {exc}")

        thread = threading.Thread(target=runner, daemon=True)
        task.thread = thread
        thread.start()
        return thread
