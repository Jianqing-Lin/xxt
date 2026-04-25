import json
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup

from core.api import Api
from core.crates.Http import Http


class Courses:
    def __init__(self, User=None):
        if User:
            self.User = User
            self.iLog = User.iLog
            self.new()

    def new(self) -> object:
        self.iLog("Courses_Get... [OK]")
        self.courses_format()
        self.User.ice.select_mode()
        self.courses_select()
        self.User.ice.configure_speed_after_course_selection()
        self.course_get()
        return self

    def courses_get(self, header, cookie, proxy=None) -> dict:
        request_headers = dict(header)
        request_headers["Referer"] = Api.Courses_Get_Referer
        with Http.Client(
            headers=request_headers,
            cookies=cookie,
            proxies=proxy,
            follow_redirects=True,
        ) as r:
            response = r.post(Api.Courses_Get, data=Api.Courses_Get_fn())
            courses = self._parse_courses(response.text)
            is_authenticated = "passport2.chaoxing.com" not in response.text and "fanyalogin" not in response.text.lower()
            self.courses = {
                "result": is_authenticated,
                "courses": courses,
                "raw": response.text,
            }
            return self.courses

    def _parse_courses(self, raw_text: str) -> list[dict]:
        parsed = self._parse_courses_from_html(raw_text)
        if parsed:
            return parsed
        return self._parse_courses_from_json(raw_text)

    def _parse_courses_from_html(self, raw_text: str) -> list[dict]:
        soup = BeautifulSoup(raw_text, "html.parser")
        parsed_courses = []
        for course in soup.select("div.course"):
            if course.select_one("a.not-open-tip") or course.select_one("div.not-open-tip"):
                continue
            href = ""
            link = course.select_one("a[href]")
            if link is not None:
                href = link.get("href", "")
            query = parse_qs(urlparse(href).query)
            classid = self._input_value(course, "clazzId")
            courseid = self._input_value(course, "courseId")
            cpi = self._query_value(query, "cpi")
            if not all((classid, courseid, cpi)):
                continue
            parsed_courses.append(
                {
                    "classid": classid,
                    "courseid": courseid,
                    "cpi": cpi,
                    "name": self._node_value(course.select_one("span.course-name")),
                    "teacher": self._node_value(course.select_one("p.color3")),
                }
            )
        return parsed_courses

    def _parse_courses_from_json(self, raw_text: str) -> list[dict]:
        try:
            payload = json.loads(raw_text)
        except ValueError:
            return []
        parsed_courses = []
        for item in payload.get("channelList", []):
            content = item.get("content", {})
            course_data = content.get("course", {}).get("data", [])
            if not course_data:
                continue
            course = course_data[0]
            parsed_courses.append(
                {
                    "classid": item.get("key", ""),
                    "courseid": course.get("id", ""),
                    "cpi": item.get("cpi", ""),
                    "name": course.get("name", ""),
                    "teacher": course.get("teacherfactor", ""),
                }
            )
        return [course for course in parsed_courses if all((course["classid"], course["courseid"], course["cpi"]))]

    def _input_value(self, course, css_class: str) -> str:
        node = course.select_one(f"input.{css_class}")
        if node is None:
            return ""
        return node.get("value", "").strip()

    def _query_value(self, query: dict, key: str) -> str:
        values = query.get(key, [])
        return values[0].strip() if values else ""

    def _node_value(self, node) -> str:
        if node is None:
            return ""
        return node.get("title", node.get_text(strip=True)).strip()

    def courses_format(self):
        self.courses_format_course = list(self.User.courses.get("courses", []))
        self.iLog(self.courses_format_course, 0)
        if not self.courses_format_course:
            self.iLog("No courses found for current account.", 4)
            quit(1)
        self.iLog("Courses_Format... [OK]")

    def courses_select(self):
        for i in range(len(self.courses_format_course)):
            course = self.courses_format_course[i]
            self.User.Format_list(i, f"{course['classid']} - {course['name']} - {course['teacher']}")
        self.iLog("Please select courses. Support multiple indexes and ranges like: 0 1 3-5")
        try:
            selections = self._parse_selection(input("Input: "))
        except Exception:
            quit(1)
        self.course_select = [self.courses_format_course[index] for index in selections]
        self.iLog(self.course_select, 0)

    def _parse_selection(self, value: str) -> list[int]:
        selections = set()
        tokens = [token for token in value.split() if token]
        if not tokens:
            raise ValueError("empty selection")
        i = 0
        while i < len(tokens):
            token = tokens[i]
            if "-" in token and token != "-":
                start, end = token.split("-", 1)
                selections.update(self._expand_range(int(start), int(end)))
                i += 1
                continue
            if i + 2 < len(tokens) and tokens[i + 1] == "-":
                selections.update(self._expand_range(int(token), int(tokens[i + 2])))
                i += 3
                continue
            selections.add(int(token))
            i += 1
        ordered = sorted(selections)
        total = len(getattr(self, "courses_format_course", []))
        if total:
            for index in ordered:
                if index < 0 or index >= total:
                    raise IndexError(index)
        return ordered

    def _expand_range(self, start: int, end: int) -> range:
        if start <= end:
            return range(start, end + 1)
        return range(end, start + 1)

    def course_get(self):
        self.course = []
        with Http.Client(
            headers=self.User.ice.headers,
            cookies=self.User.cookie,
            proxies=self.User.ice.proxy,
            follow_redirects=True,
        ) as r:
            for course in self.course_select:
                response = r.get(
                    Api.Course_Get,
                    params=Api.Course_GET_fn(course["courseid"], course["classid"], course["cpi"]),
                )
                if response.status_code != 200:
                    self.iLog("Get Course name... [Error]", 3)
                    self.iLog("Please check iLog.txt or open Debug", 4)
                    quit(1)
                self.iLog(f"Get Course name: {course['name']}... [OK]")
                self.course.append(
                    {
                        **course,
                        "html": response.text,
                    }
                )
        self.iLog(self.course, 0)
        return self.course
