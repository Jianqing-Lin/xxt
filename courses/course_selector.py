class CourseSelector:
    def __init__(self, printer=print):
        self.printer = printer

    def format_list(self, courses: list[dict], formatter):
        for index, course in enumerate(courses):
            formatter(index, f"{course['classid']} - {course['name']} - {course['teacher']}")

    def parse_selection(self, value: str, total: int) -> list[int]:
        selections = set()
        tokens = [token for token in value.split() if token]
        if not tokens:
            raise ValueError("empty selection")
        i = 0
        while i < len(tokens):
            token = tokens[i]
            if "-" in token and token != "-":
                start, end = token.split("-", 1)
                selections.update(self.expand_range(int(start), int(end)))
                i += 1
                continue
            if i + 2 < len(tokens) and tokens[i + 1] == "-":
                selections.update(self.expand_range(int(token), int(tokens[i + 2])))
                i += 3
                continue
            selections.add(int(token))
            i += 1
        ordered = sorted(selections)
        for index in ordered:
            if index < 0 or index >= total:
                raise IndexError(index)
        return ordered

    def expand_range(self, start: int, end: int) -> range:
        if start <= end:
            return range(start, end + 1)
        return range(end, start + 1)
