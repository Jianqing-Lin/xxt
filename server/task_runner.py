from courses.course_repository import CourseRepository
from model.course import Course
from server.course_service import WebCourseService
from server.runtime import WebLogger, build_web_runtime


class WebIceProxy:
    def __init__(self, runtime, logger):
        self.runtime = runtime
        self.iLog = logger.log
        self.headers = runtime.headers
        self.proxy = runtime.proxy
        self.speed = runtime.speed
        self.mode = runtime.mode
        self.collect_tiku = runtime.collect_tiku
        self.collect_threads = runtime.collect_threads
        self.tiku_url = runtime.tiku_url
        self.tiku_use = runtime.tiku_use
        self.tiku_tokens = runtime.tiku_tokens
        self.collect_sources = runtime.collect_sources


class WebUserProxy:
    def __init__(self, ice, cookie: dict, courses_payload: dict):
        self.ice = ice
        self.iLog = ice.iLog
        self.cookie = cookie
        self.courses = courses_payload
        self.Format_list = lambda k, v: self.iLog(f"| {k}\t| {v}\t|")


class WebCoursesProxy:
    def __init__(self, user, selected_courses: list[dict]):
        self.User = user
        self.iLog = user.iLog
        self.courses_format_course = selected_courses
        self.course = selected_courses


class WebTaskRunner:
    def __init__(self, emit_log=None):
        self.logger = WebLogger(emit=emit_log)

    def run(self, *, username: str, password: str, course_indexes: list[int], mode: str, speed=None, collect_threads: int = 1, tiku_url: str = "", tiku_use: str = "", tiku_tokens=None, collect_sources=None) -> dict:
        runtime = build_web_runtime(
            logger=self.logger.log,
            tiku_url=tiku_url,
            tiku_use=tiku_use,
            tiku_tokens=tiku_tokens or {},
            speed=speed,
            collect_threads=collect_threads,
            mode=mode,
            collect_sources=collect_sources,
        )
        runtime.collect_tiku = mode == "collect"
        runtime.speed = 1.0 if runtime.collect_tiku else runtime.normalize_speed(speed or 1.0)
        runtime.collect_threads = runtime.normalize_collect_threads(collect_threads)
        service = WebCourseService(emit_log=self.logger.log)
        cookie = service.login_and_get_cookie(username, password)
        repository = CourseRepository(runtime, cookie)
        try:
            courses_payload = repository.fetch_course_list()
            all_courses = courses_payload.get("courses", [])
            if not course_indexes:
                selected = all_courses
            else:
                selected = [all_courses[index] for index in course_indexes if 0 <= index < len(all_courses)]
            loaded = [repository.fetch_course_page(course) for course in selected]
        finally:
            repository.close()
        ice = WebIceProxy(runtime, self.logger)
        user = WebUserProxy(ice, cookie, courses_payload)
        courses = WebCoursesProxy(user, loaded)
        course_runner = Course(courses)
        return {
            "mode": mode,
            "course_count": len(loaded),
            "summary": getattr(course_runner, "summary", {}),
        }
