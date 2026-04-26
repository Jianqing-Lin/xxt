from collections import defaultdict, deque
from threading import Lock


class LogBuffer:
    def __init__(self, max_lines: int = 2000):
        self.max_lines = max_lines
        self._logs = defaultdict(lambda: deque(maxlen=self.max_lines))
        self._lock = Lock()

    def append(self, task_id: str, line: str):
        with self._lock:
            self._logs[task_id].append(str(line))

    def extend(self, task_id: str, lines: list[str]):
        with self._lock:
            for line in lines:
                self._logs[task_id].append(str(line))

    def get(self, task_id: str) -> list[str]:
        with self._lock:
            return list(self._logs.get(task_id, []))

    def clear(self, task_id: str):
        with self._lock:
            self._logs.pop(task_id, None)
