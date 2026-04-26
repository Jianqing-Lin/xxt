import httpx
from typing import Any, Optional


class SessionFactory:
    def __init__(self, headers: Optional[dict] = None, cookies: Optional[dict] = None, proxy: Any = None, follow_redirects: bool = True, timeout: float = 20.0):
        self.headers = dict(headers or {})
        self.cookies = dict(cookies or {})
        self.proxy = proxy
        self.follow_redirects = follow_redirects
        self.timeout = timeout
        self._shared_client: Optional[httpx.Client] = None

    def build(self, shared: bool = False, **overrides) -> httpx.Client:
        if shared and not overrides:
            return self.get_shared_client()
        options = self._build_options(**overrides)
        return httpx.Client(**options)

    def get_shared_client(self) -> httpx.Client:
        if self._shared_client is None:
            self._shared_client = httpx.Client(**self._build_options())
        return self._shared_client

    def close(self):
        if self._shared_client is not None:
            self._shared_client.close()
            self._shared_client = None

    def with_cookies(self, cookies: Optional[dict]):
        return SessionFactory(
            headers=self.headers,
            cookies=cookies or {},
            proxy=self.proxy,
            follow_redirects=self.follow_redirects,
            timeout=self.timeout,
        )

    def _build_options(self, **overrides) -> dict:
        options = {
            "headers": dict(self.headers),
            "cookies": dict(self.cookies),
            "follow_redirects": self.follow_redirects,
            "timeout": self.timeout,
        }
        options.update(overrides)
        proxies = options.pop("proxies", None)
        proxy = options.pop("proxy", None)
        if proxy is None:
            proxy = self._resolve_proxy(proxies if proxies is not None else self.proxy)
        if proxy is not None:
            options["proxy"] = proxy
        return options

    def _resolve_proxy(self, proxies: Any):
        if not proxies:
            return None
        if isinstance(proxies, dict):
            proxy = proxies.get("https://") or proxies.get("http://")
            if proxy is None and proxies:
                proxy = next(iter(proxies.values()))
            return proxy
        return proxies
