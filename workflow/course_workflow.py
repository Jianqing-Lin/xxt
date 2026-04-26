class CourseWorkflow:
    def __init__(self, repository, selector, logger, formatter, runtime):
        self.repository = repository
        self.selector = selector
        self.log = logger
        self.formatter = formatter
        self.runtime = runtime

    def close(self):
        close = getattr(self.repository, "close", None)
        if callable(close):
            close()

    def prepare_courses(self, courses_payload: dict) -> list[dict]:
        courses = list(courses_payload.get("courses", []))
        self.log(courses, 0)
        if not courses:
            self.log("No courses found for current account.", 4)
            raise SystemExit(1)
        self.log("Courses_Format... [OK]")
        return courses

    def select_courses(self, courses: list[dict]) -> list[dict]:
        self.selector.format_list(courses, self.formatter)
        self.log("Please select courses. Support multiple indexes and ranges like: 0 1 3-5")
        try:
            selections = self.selector.parse_selection(input("Input: "), len(courses))
        except Exception:
            raise SystemExit(1)
        selected = [courses[index] for index in selections]
        self.log(selected, 0)
        return selected

    def load_course_pages(self, selected_courses: list[dict]) -> list[dict]:
        loaded = []
        for course in selected_courses:
            page = self.repository.fetch_course_page(course)
            if page["status_code"] != 200:
                self.log("Get Course name... [Error]", 3)
                self.log("Please check iLog.txt or open Debug", 4)
                raise SystemExit(1)
            self.log(f"Get Course name: {course['name']}... [OK]")
            loaded.append({**course, "html": page["html"]})
        self.log(loaded, 0)
        return loaded

    def run(self, courses_payload: dict) -> tuple[list[dict], list[dict]]:
        formatted = self.prepare_courses(courses_payload)
        self.runtime.select_mode()
        selected = self.select_courses(formatted)
        self.runtime.configure_speed_after_course_selection()
        return formatted, self.load_course_pages(selected)
