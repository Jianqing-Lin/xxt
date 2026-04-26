from core.crates.Http import Http


class TikuAdapterClient:
    def __init__(self, adapter_url: str, use: str = "", tokens=None, proxy=None):
        self.adapter_url = adapter_url
        self.use = use
        self.tokens = tokens or {}
        self.proxy = proxy
        self.last_error = ""
        self.last_payload = None

    def _query_adapter_service(self, client, payload: dict):
        params = {"noRecord": "1"}
        if self.use:
            params["use"] = self.use
        params.update(self.tokens)
        return client.post(self.adapter_url, params=params, json=payload)

    def _query_reference_tikuadapter(self, client, payload: dict):
        data = {
            "question": payload.get("question", ""),
            "type": payload.get("type", 4),
            "options": payload.get("options", []),
        }
        token = self.tokens.get("token") or self.tokens.get("tokens") or self.tokens.get("api_key")
        if token:
            data["token"] = token
        if self.use:
            data["provider"] = self.use.split(",")[0].strip()
        return client.post(self.adapter_url, json=data)

    def query(self, payload: dict):
        self.last_error = ""
        self.last_payload = None
        if not self.adapter_url:
            self.last_error = "adapter url empty"
            return None
        try:
            with Http.Client(proxies=self.proxy, follow_redirects=True, timeout=12) as client:
                if "adapter-service/search" in self.adapter_url:
                    response = self._query_adapter_service(client, payload)
                else:
                    response = self._query_reference_tikuadapter(client, payload)
        except Exception as exc:
            self.last_error = f"adapter request failed: {exc}"
            return None
        if response.status_code != 200:
            self.last_error = f"adapter status {response.status_code}: {response.text[:200]}"
            return None
        try:
            self.last_payload = response.json()
            return self.last_payload
        except ValueError:
            self.last_error = f"adapter invalid json: {response.text[:200]}"
            return None
