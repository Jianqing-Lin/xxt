from auth.auth_service import AuthService
from auth.cookie_store import CookieStore
from courses.course_repository import CourseRepository
from server.runtime import WebLogger, build_web_runtime


class WebCourseService:
    def __init__(self, emit_log=None):
        self.logger = WebLogger(emit=emit_log)
        self.runtime = build_web_runtime(logger=self.logger.log)
        self.cookie_store = CookieStore("config/cookies.json")
        self.auth_service = AuthService(self.runtime)

    def login_and_get_cookie(self, username: str, password: str) -> dict:
        cookies = self.cookie_store.read_all()
        cached = cookies.get(username)
        if cached and self.auth_service.validate_cookie(cached):
            self.logger.log("Cookie... [OK]")
            return dict(cached)
        self.logger.log("Cookie... [Refresh]", 2)
        cookie = self.auth_service.login(username, password)
        cookies[username] = dict(cookie)
        self.cookie_store.write_all(cookies)
        return dict(cookie)

    def list_courses(self, username: str, password: str) -> dict:
        cookie = self.login_and_get_cookie(username, password)
        repository = CourseRepository(self.runtime, cookie)
        try:
            payload = repository.fetch_course_list()
        finally:
            repository.close()
        self.logger.log(f"Courses fetched: {len(payload.get('courses', []))}")
        return payload
