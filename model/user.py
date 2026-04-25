'''
Login and encryption thanks to 'Samueli924/chaoxing'
    Project(https://github.com/Samueli924/chaoxing)
'''
import getpass
import os
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from core.crates.Config import Read, Write
    from model.courses import Courses
else:
    from core.crates.Config import Read, Write
    from .courses import Courses


def Header() -> dict:
    return {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36 Edg/129.0.0.0',
        'sec-ch-ua': '"Microsoft Edge";v="129", "Not=A?Brand";v="8", "Chromium";v="129"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        }


def User_hide(user: str) -> str:
    if len(user) <= 7:
        return user[0:1] + "****"
    return user[0:3] + "****" + user[-4:]


def Format_list(k, v):
    print(f"| {k}\t| {v}\t|")


def Cookie_validity(header, cookie, proxy=None) -> bool:
   res = Courses().courses_get(header, cookie, proxy)
   return bool(res['result'])


class User:
    def __init__(self, ice):
        self.FILE_COOKIE = "config/cookies.json"
        self.ice = ice
        self.iLog = ice.iLog
        self.Format_list = Format_list
        self.Courses = Courses()
        self.new()

    def new(self) -> object:
        self.cookies = Read(self.FILE_COOKIE)
        self.stdin()
        self.new_cookie()
        return self

    def new_re(self):
        self.iLog(self.new_cookie(), 0)

    def stdin(self) -> dict:
        try:
            self.user = input("User: ").strip()
        except EOFError:
            self.iLog("No interactive stdin available for User input.", 4)
            quit(1)
        if not self.user:
            self.iLog("User is required.", 4)
            quit(1)
        try:
            self.passwd = getpass.getpass("Passwd: ")
        except EOFError:
            self.iLog("No interactive stdin available for Passwd input.", 4)
            quit(1)
        if not self.passwd:
            self.iLog("Passwd is required.", 4)
            quit(1)
        self.iLog(f"Login user: {User_hide(self.user)}")
        return {
            "user": self.user,
        }

    def new_cookie(self):
        def use_cookie(self):
            self.courses = self.Courses.courses_get(self.ice.headers, self.cookies[self.user], self.ice.proxy)
            self.iLog(self.courses, 0)
            self.cookie = self.cookies[self.user]
            if self.courses['result']:
                self.iLog("Cookie...  [OK]")
                self.iLog(self.cookie, 0)
            else:
                self.iLog("Cookie... [Error]")
                quit(1)

        if self.user in self.cookies and Cookie_validity(self.ice.headers, self.cookies[self.user], self.ice.proxy):
            use_cookie(self)
            return

        self.iLog("Cookie... [Refresh]", 2)
        self.cookie = self.ice.login(self.user, self.passwd)
        self.iLog(self.cookie, 0)
        self.cookies[self.user] = dict(self.cookie)
        self.iLog(Write(self.FILE_COOKIE, self.cookies), 0)
        use_cookie(self)
