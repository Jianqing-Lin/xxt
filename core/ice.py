from .api import Api
from .error import Error
from .crates.Logo import Logo
from .crates.Http import Http
from .crates.Log import iLog
from .crates.Version import Version
from .args import Args
from .update import Update
from model.user import Header

def iLog_new(ice, iLog):
    iLog = iLog(1, "config/iLog.log")
    iLog.level = not ice.debug
    iLog.LINE = ice.debug
    iLog.MODEL = ice.debug
    iLog.PATH = ice.debug
    iLog = iLog.log
    ice.iLog = iLog

def nlog():
    ...

class ice_study:
    VERSION = Version.version
    def __init__(self, main=None, proxy=None, v=True):
        res = Args()
        Logo(v and res['logo'])
        self.debug = res['debug']
        self.beta = res['beta']
        self.speed_arg = res.get('speed')
        self.speed = 1.0
        self.mode = "study"
        self.collect_tiku = False
        self.tiku_url = res.get('tiku_url')
        self.tiku_use = res.get('tiku_use')
        self.tiku_tokens = self._parse_tiku_tokens(res.get('tiku_token', []))
        iLog_new(self,iLog)
        Update(self.iLog, res['update'])
        if res['v']:
            self.iLog(self.VERSION)
            quit(0)
        self.headers = Header()
        self.proxy = proxy
        self.iLog(res, 0)
        self.iLog(f"Playback speed: {self.speed}x")
        self.iLog(f"Tiku adapter: {self.tiku_url} use={self.tiku_use}")
        self.iLog("Welcome to " + self.VERSION)
        self.iLog(f"\nVerison: {v}\nHeader: {self.headers}\nProxy: {self.proxy}\n", 0)

    def _normalize_speed(self, value):
        try:
            speed = float(value)
        except (TypeError, ValueError):
            speed = 1.0
        return max(0.25, min(16.0, speed))

    def _prompt_speed(self):
        try:
            raw = input("Playback speed (default 1.0): ").strip()
        except EOFError:
            return 1.0
        if not raw:
            return 1.0
        return self._normalize_speed(raw)

    def select_mode(self):
        try:
            raw = input("Mode: 1) 刷课  2) 收录题库 [1]: ").strip()
        except EOFError:
            raw = "1"
        if raw == "2":
            self.mode = "collect"
            self.collect_tiku = True
        else:
            self.mode = "study"
            self.collect_tiku = False
        self.iLog(f"Run mode: {'收录题库' if self.collect_tiku else '刷课'}")
        return self.mode

    def configure_speed_after_course_selection(self):
        if self.collect_tiku:
            self.speed = 1.0
            return self.speed
        if self.speed_arg is None:
            self.speed = self._prompt_speed()
        else:
            self.speed = self._normalize_speed(self.speed_arg)
        self.iLog(f"Playback speed: {self.speed}x")
        return self.speed

    def _parse_tiku_tokens(self, pairs):
        tokens = {}
        for pair in pairs or []:
            if "=" not in pair:
                continue
            key, value = pair.split("=", 1)
            key = key.strip()
            if key:
                tokens[key] = value.strip()
        return tokens

    def login(self, user: str, password: str):
        data = Api.Login_fn(user, password)
        self.iLog(f"\n[POST]: {Api.Login}\nData: {data}\n", 0)
        with Http.Client(headers=self.headers, proxies=self.proxy, follow_redirects=True) as r:
            res = r.post(Api.Login, data=data)
            self.iLog(f"\nRes: {res.text}\n", 0)
            try:
                res_json = res.json()
            except ValueError:
                self.iLog("Login status... [Invalid Response]", 4)
                self.iLog(f"Error Res: {res.text}", 4)
                quit(0)
            if not res_json.get("status"):
                self.iLog("Login status... [False]", 4)
                self.iLog(f"Error Res: {res.text}", 4)
                quit(0)
            self.iLog("Login status... [True]")
            self.cookie = dict(res.cookies.items())
            self.iLog(f"\nCookie: {self.cookie}\n", 0)
            return self.cookie
