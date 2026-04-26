from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class RuntimeContext:
    """Shared runtime state for the current execution flow."""

    version: str
    debug: bool = False
    beta: bool = False
    speed_arg: Optional[float] = None
    speed: float = 1.0
    mode: str = "study"
    collect_tiku: bool = False
    collect_threads: int = 1
    collect_sources: set[str] = field(default_factory=lambda: {"chapter_quiz", "homework", "exam", "unknown"})
    tiku_url: str = ""
    tiku_use: str = ""
    tiku_tokens: dict[str, str] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    proxy: Any = None
    logger: Optional[Callable[..., Any]] = None

    def log(self, text: Any, level: int = 1, end: str = "\n"):
        if self.logger is None:
            return None
        return self.logger(text, level, end)

    def normalize_speed(self, value: Any) -> float:
        try:
            speed = float(value)
        except (TypeError, ValueError):
            speed = 1.0
        return max(0.25, min(16.0, speed))

    def normalize_collect_threads(self, value: Any) -> int:
        try:
            threads = int(value)
        except (TypeError, ValueError):
            threads = 1
        return max(1, min(32, threads))

    def prompt_speed(self) -> float:
        try:
            raw = input("Playback speed (default 1.0): ").strip()
        except EOFError:
            return 1.0
        if not raw:
            return 1.0
        return self.normalize_speed(raw)

    def select_mode(self) -> str:
        try:
            raw = input("Mode: 1) 刷课  2) 收录题库 [1]: ").strip()
        except EOFError:
            raw = "1"
        if raw == "2":
            self.mode = "collect"
            self.collect_tiku = True
        else:
            self.mode = "study"
            self.collect_tiku = False
        self.log(f"Run mode: {'收录题库' if self.collect_tiku else '刷课'}")
        return self.mode

    def configure_speed_after_course_selection(self) -> float:
        if self.collect_tiku:
            self.speed = 1.0
            return self.speed
        if self.speed_arg is None:
            self.speed = self.prompt_speed()
        else:
            self.speed = self.normalize_speed(self.speed_arg)
        self.log(f"Playback speed: {self.speed}x")
        return self.speed
