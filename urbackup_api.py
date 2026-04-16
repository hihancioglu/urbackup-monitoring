import requests


class UrBackupAPI:
    def __init__(self, base_url: str, username: str, password: str, lang: str = "tr"):
        if not base_url:
            raise ValueError("URB_URL/base_url is required")
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.lang = lang
        self.session = requests.Session()
        self.session_token = None
        self.login()

    def login(self):
        response = self.session.post(
            f"{self.base_url}/x?a=login",
            data={
                "username": self.username,
                "password": self.password,
                "plainpw": "1",
            },
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()

        token = data.get("session")
        if not token:
            raise RuntimeError(f"Login failed: {data}")

        self.session_token = token
        return token

    def _post_raw(self, action: str, data: dict):
        return self.session.post(
            f"{self.base_url}/x?a={action}",
            headers={
                "X-Requested-With": "XMLHttpRequest",
                "Referer": self.base_url + "/",
            },
            data=data,
            timeout=20,
        )

    def _safe_post(self, action: str, payload: dict | None = None):
        payload = payload or {}

        for attempt in (1, 2):
            if attempt == 2:
                self.login()

            body = {
                **payload,
                "ses": self.session_token,
                "lang": self.lang,
            }
            try:
                response = self._post_raw(action, body)
            except requests.RequestException:
                continue

            if response.status_code != 200:
                continue

            raw = response.text.strip()
            if not raw or raw.startswith("<"):
                continue

            try:
                data = response.json()
            except ValueError:
                continue

            # UrBackup may return {"error": 1} when the session is expired.
            # In that case refresh session and retry once.
            if isinstance(data, dict) and data.get("error") == 1:
                continue

            return data

        return {}

    def usage(self):
        return self._safe_post("usage")

    def status(self):
        return self._safe_post("status")

    def progress(self, *, include_lastacts: bool = False, raw: bool = False):
        data = self._safe_post("progress", {"with_lastacts": 1 if include_lastacts else 0})
        if raw:
            return data
        return data.get("progress", [])

    def logs(self, client_id=None, log_id=None, ll: int = 0):
        payload = {"ll": ll}
        if client_id is not None:
            payload["filter"] = client_id
        if log_id is not None:
            payload["logid"] = log_id
        return self._safe_post("logs", payload)
