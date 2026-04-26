from courses.course_repository import CourseRepository
from courses.course_selector import CourseSelector
from parsers.course_parser import CourseParser
from workflow.course_workflow import CourseWorkflow


def _build_runtime_proxy(header, proxy=None):
    class RuntimeProxy:
        def __init__(self, headers, proxy):
            self.headers = headers
            self.proxy = proxy

    return RuntimeProxy(header, proxy)


class Courses:
    def __init__(self, User=None):
        self.parser = CourseParser()
        self.selector = CourseSelector()
        if User:
            self.User = User
            self.iLog = User.iLog
            self.repository = CourseRepository(User.ice.runtime, User.cookie)
            self.workflow = CourseWorkflow(
                repository=self.repository,
                selector=self.selector,
                logger=self.iLog,
                formatter=self.User.Format_list,
                runtime=self.User.ice.runtime,
            )
            self.new()

    def new(self) -> object:
        self.iLog("Courses_Get... [OK]")
        try:
            self.courses_format_course, self.course = self.workflow.run(self.User.courses)
            self.User.ice.mode = self.User.ice.runtime.mode
            self.User.ice.collect_tiku = self.User.ice.runtime.collect_tiku
            self.User.ice.speed = self.User.ice.runtime.speed
            return self
        finally:
            close = getattr(self.workflow, "close", None)
            if callable(close):
                close()

    def courses_get(self, header, cookie, proxy=None) -> dict:
        runtime = _build_runtime_proxy(header, proxy)
        repository = CourseRepository(runtime, cookie)
        try:
            return repository.fetch_course_list()
        finally:
            repository.close()
