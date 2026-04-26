from app.runtime import RuntimeContext
from clients.auth_client import AuthClient
from model.user import Header
from .api import Api
from .args import Args
from .crates.Log import iLog
from .crates.Logo import Logo
from .crates.Version import Version
from .update import Update


def iLog_new(ice, iLogClass):
    logger = iLogClass(1, "config/iLog.log")
    logger.level = not ice.debug
    logger.LINE = ice.debug
    logger.MODEL = ice.debug
    logger.PATH = ice.debug
    ice.iLog = logger.log


def nlog():
    ...


def parse_tiku_tokens(pairs):
    tokens = {}
    for pair in pairs or []:
        if "=" not in pair:
            continue
        key, value = pair.split("=", 1)
        key = key.strip()
        if key:
            tokens[key] = value.strip()
    return tokens


def build_runtime(version: str, args: dict, proxy, logger):
    return RuntimeContext(
        version=version,
        debug=args["debug"],
        beta=args["beta"],
        speed_arg=args.get("speed"),
        speed=1.0,
        mode="study",
        collect_tiku=False,
        collect_threads=1,
        tiku_url=args.get("tiku_url"),
        tiku_use=args.get("tiku_use"),
        tiku_tokens=parse_tiku_tokens(args.get("tiku_token", [])),
        headers=Header(),
        proxy=proxy,
        logger=logger,
    )


class ice_study:
    VERSION = Version.version

    def __init__(self, main=None, proxy=None, v=True):
        args = Args()
        Logo(v and args["logo"])
        self.debug = args["debug"]
        self.beta = args["beta"]
        iLog_new(self, iLog)
        Update(self.iLog, args["update"])
        if args["v"]:
            self.iLog(self.VERSION)
            quit(0)
        self.proxy = proxy
        self.runtime = build_runtime(self.VERSION, args, proxy, self.iLog)
        self._sync_from_runtime()
        self.iLog(args, 0)
        self.iLog(f"Playback speed: {self.speed}x")
        self.iLog(f"Tiku adapter: {self.tiku_url} use={self.tiku_use}")
        self.iLog("Welcome to " + self.VERSION)
        self.iLog(f"\nVerison: {v}\nHeader: {self.headers}\nProxy: {self.proxy}\n", 0)

    def _sync_from_runtime(self):
        self.debug = self.runtime.debug
        self.beta = self.runtime.beta
        self.speed_arg = self.runtime.speed_arg
        self.speed = self.runtime.speed
        self.mode = self.runtime.mode
        self.collect_tiku = self.runtime.collect_tiku
        self.collect_threads = self.runtime.collect_threads
        self.tiku_url = self.runtime.tiku_url
        self.tiku_use = self.runtime.tiku_use
        self.tiku_tokens = self.runtime.tiku_tokens
        self.headers = self.runtime.headers
        self.proxy = self.runtime.proxy

    def _normalize_speed(self, value):
        return self.runtime.normalize_speed(value)

    def _prompt_speed(self):
        return self.runtime.prompt_speed()

    def select_mode(self):
        self.runtime.select_mode()
        self._sync_from_runtime()
        return self.mode

    def configure_speed_after_course_selection(self):
        self.runtime.configure_speed_after_course_selection()
        self._sync_from_runtime()
        return self.speed

    def login(self, user: str, password: str):
        data = Api.Login_fn(user, password)
        self.iLog(f"\n[POST]: {Api.Login}\nData: {data}\n", 0)
        client = AuthClient(headers=self.headers, proxy=self.proxy)
        res = client.login(user, password)
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
