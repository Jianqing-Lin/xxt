from core.crates.Config import Read, Write


class CookieStore:
    def __init__(self, path: str = "config/cookies.json"):
        self.path = path

    def read_all(self) -> dict:
        return Read(self.path)

    def write_all(self, cookies: dict) -> dict:
        return Write(self.path, cookies)
