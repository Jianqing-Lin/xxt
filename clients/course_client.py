from clients.session import SessionFactory
from core.api import Api


class CourseClient:
    def __init__(self, headers=None, cookies=None, proxy=None, session_factory=None):
        self.headers = dict(headers or {})
        self.cookies = dict(cookies or {})
        self.proxy = proxy
        self.session_factory = session_factory or SessionFactory(
            headers=self.headers,
            cookies=self.cookies,
            proxy=self.proxy,
            follow_redirects=True,
        )
        self.client = self.session_factory.get_shared_client()

    def close(self):
        self.session_factory.close()

    def get_course_list(self):
        request_headers = dict(self.headers)
        request_headers["Referer"] = Api.Courses_Get_Referer
        return self.client.post(Api.Courses_Get, data=Api.Courses_Get_fn(), headers=request_headers)

    def get_course_page(self, courseid, classid, cpi):
        return self.client.get(
            Api.Course_Get,
            params=Api.Course_GET_fn(courseid, classid, cpi),
        )
