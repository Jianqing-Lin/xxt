class JobDispatcher:
    def __init__(self, handlers: dict[str, callable], logger):
        self.handlers = handlers
        self.log = logger

    def dispatch(self, job_type: str, *args, **kwargs):
        handler = self.handlers.get(job_type)
        if handler is None:
            self.log(f"Unknown job type: {job_type}", 2)
            return None
        return handler(*args, **kwargs)
