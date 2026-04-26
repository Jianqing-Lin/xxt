from app.runtime import RuntimeContext
from model.user import Header


class WebLogger:
    def __init__(self, emit=None):
        self.emit = emit
        self.lines: list[str] = []

    def log(self, text, level: int = 1, end: str = "\n"):
        line = str(text)
        self.lines.append(line)
        if self.emit is not None:
            self.emit(line)
        return True


def build_web_runtime(logger=None, *, proxy=None, tiku_url: str = "", tiku_use: str = "", tiku_tokens=None, speed=None, mode: str = "study"):
    return RuntimeContext(
        version="web",
        debug=False,
        beta=False,
        speed_arg=speed,
        speed=1.0 if speed is None else float(speed),
        mode=mode,
        collect_tiku=mode == "collect",
        tiku_url=tiku_url,
        tiku_use=tiku_use,
        tiku_tokens=tiku_tokens or {},
        headers=Header(),
        proxy=proxy,
        logger=logger,
    )
