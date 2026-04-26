from core.api import Api
from core.crates.Http import Http


class AuthClient:
    def __init__(self, headers=None, proxy=None):
        self.headers = dict(headers or {})
        self.proxy = proxy

    def login(self, user: str, password: str):
        data = Api.Login_fn(user, password)
        with Http.Client(headers=self.headers, proxies=self.proxy, follow_redirects=True) as client:
            return client.post(Api.Login, data=data)
