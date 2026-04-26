from clients.auth_client import AuthClient
from clients.course_client import CourseClient


class AuthService:
    def __init__(self, runtime):
        self.runtime = runtime
        self.log = runtime.log
        self.auth_client = AuthClient(headers=runtime.headers, proxy=runtime.proxy)

    def login(self, user: str, password: str) -> dict:
        data = self.auth_client.login(user, password)
        self.log(f"\nRes: {data.text}\n", 0)
        try:
            payload = data.json()
        except ValueError:
            self.log("Login status... [Invalid Response]", 4)
            self.log(f"Error Res: {data.text}", 4)
            raise SystemExit(0)
        if not payload.get("status"):
            self.log("Login status... [False]", 4)
            self.log(f"Error Res: {data.text}", 4)
            raise SystemExit(0)
        self.log("Login status... [True]")
        return dict(data.cookies.items())

    def validate_cookie(self, cookie: dict) -> bool:
        response = CourseClient(
            headers=self.runtime.headers,
            cookies=cookie,
            proxy=self.runtime.proxy,
        ).get_course_list()
        text = response.text
        return "passport2.chaoxing.com" not in text and "fanyalogin" not in text.lower()
