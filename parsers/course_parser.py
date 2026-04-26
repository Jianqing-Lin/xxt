import json
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup


class CourseParser:
    def parse_course_list(self, raw_text: str) -> list[dict]:
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
