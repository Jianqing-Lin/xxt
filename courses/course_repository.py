from clients.course_client import CourseClient
from parsers.course_parser import CourseParser


class CourseRepository:
    def __init__(self, runtime, cookie: dict):
        self.runtime = runtime
        self.cookie = dict(cookie or {})
        self.client = CourseClient(headers=runtime.headers, cookies=self.cookie, proxy=runtime.proxy)
        self.parser = CourseParser()

    def close(self):
        close = getattr(self.client, "close", None)
        if callable(close):
            close()

    def fetch_course_list(self) -> dict:
        response = self.client.get_course_list()
        courses = self.parser.parse_course_list(response.text)
        is_authenticated = "passport2.chaoxing.com" not in response.text and "fanyalogin" not in response.text.lower()
        return {
            "result": is_authenticated,
            "courses": courses,
            "raw": response.text,
        }

    def fetch_course_page(self, course: dict) -> dict:
        response = self.client.get_course_page(course["courseid"], course["classid"], course["cpi"])
        return {
            **course,
            "html": response.text,
            "status_code": response.status_code,
        }
