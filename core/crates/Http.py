import httpx


class Http:
    @staticmethod
    def Client(*args, **kwargs):
        proxies = kwargs.pop("proxies", None)
        if proxies:
            if isinstance(proxies, dict):
                proxy = proxies.get("https://") or proxies.get("http://")
                if proxy is None and proxies:
                    proxy = next(iter(proxies.values()))
            else:
                proxy = proxies
            if proxy is not None:
                kwargs["proxy"] = proxy
        return httpx.Client(*args, **kwargs)
