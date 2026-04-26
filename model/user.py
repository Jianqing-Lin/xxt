from auth.auth_service import AuthService
from auth.cookie_store import CookieStore
from auth.input_provider import InputProvider
from courses.course_repository import CourseRepository


DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36 Edg/129.0.0.0',
    'sec-ch-ua': '"Microsoft Edge";v="129", "Not=A?Brand";v="8", "Chromium";v="129"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
}


def Header() -> dict:
    return dict(DEFAULT_HEADERS)


def User_hide(user: str) -> str:
    if len(user) <= 7:
        return user[0:1] + "****"
    return user[0:3] + "****" + user[-4:]


def Format_list(k, v):
    print(f"| {k}\t| {v}\t|")


def _build_runtime_proxy(header, proxy=None):
    class RuntimeProxy:
        def __init__(self, headers, proxy):
            self.headers = headers
            self.proxy = proxy

    return RuntimeProxy(header, proxy)


def Cookie_validity(header, cookie, proxy=None) -> bool:
    runtime = _build_runtime_proxy(header, proxy)
    auth = AuthService(runtime)
    return auth.validate_cookie(cookie)


class User:
    def __init__(self, ice):
        self.FILE_COOKIE = "config/cookies.json"
        self.ice = ice
        self.iLog = ice.iLog
        self.Format_list = Format_list
        self.cookie_store = CookieStore(self.FILE_COOKIE)
        self.input_provider = InputProvider(self.iLog)
        self.auth_service = AuthService(ice.runtime)
        self.new()

    def new(self) -> object:
        self.cookies = self.cookie_store.read_all()
        self.stdin()
        self.new_cookie()
        return self

    def new_re(self):
        self.iLog(self.new_cookie(), 0)

    def stdin(self) -> dict:
        self.user, self.passwd = self.input_provider.read_credentials()
        self.iLog(f"Login user: {User_hide(self.user)}")
        return {
            "user": self.user,
        }

    def _load_courses_from_cookie(self, cookie: dict):
        repository = CourseRepository(self.ice.runtime, cookie)
        try:
            self.courses = repository.fetch_course_list()
        finally:
            repository.close()
        self.iLog(self.courses, 0)
        self.cookie = cookie
        if self.courses['result']:
            self.iLog("Cookie...  [OK]")
            self.iLog(self.cookie, 0)
            return
        self.iLog("Cookie... [Error]")
        raise SystemExit(1)

    def new_cookie(self):
        if self.user in self.cookies and self.auth_service.validate_cookie(self.cookies[self.user]):
            self._load_courses_from_cookie(self.cookies[self.user])
            return

        self.iLog("Cookie... [Refresh]", 2)
        self.cookie = self.auth_service.login(self.user, self.passwd)
        self.iLog(self.cookie, 0)
        self.cookies[self.user] = dict(self.cookie)
        self.iLog(self.cookie_store.write_all(self.cookies), 0)
        self._load_courses_from_cookie(self.cookie)
