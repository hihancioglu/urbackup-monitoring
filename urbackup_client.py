import requests


class UrBackupClient:
    def __init__(self, base, username, password):
        self.base = base.rstrip("/")
        self.username = username
        self.password = password
        self.s = requests.Session()
        self.session = None
        self.login()

    def login(self):
        print("LOGIN...")

        r = self.s.post(
            f"{self.base}/x?a=login",
            data={
                "username": self.username,
                "password": self.password,
                "plainpw": "1",
            },
            timeout=15,
        )

        print("LOGIN STATUS:", r.status_code)
        print("LOGIN RAW:", r.text[:300])

        data = r.json()

        if not data.get("session"):
            raise Exception(f"Login failed: {data}")

        self.session = data["session"]
        print("SESSION OK")

    def _post_raw(self, action, body):
        return self.s.post(
            f"{self.base}/x?a={action}",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": self.base + "/",
            },
            data=body,
            timeout=20,
        )

    def _safe_post(self, action, body):
        for attempt in (1, 2):
            if attempt == 2:
                print(f"RELOGIN BEFORE RETRY: action={action}")
                self.login()

            r = self._post_raw(action, body)

            print(f"[{action}] attempt={attempt} status={r.status_code}")
            raw = r.text.strip()
            print(f"[{action}] raw={raw[:300]}")

            if r.status_code != 200:
                continue

            if not raw:
                continue

            if raw.startswith("<"):
                continue

            try:
                return r.json()
            except Exception as e:
                print(f"[{action}] JSON parse failed: {e}")
                continue

        print(f"[{action}] FAILED AFTER RETRY")
        return {}

    def get_usage(self):
        return self._safe_post(
            "usage",
            f"ses={self.session}&lang=tr",
        )

    def get_status(self):
        return self._safe_post(
            "status",
            f"ses={self.session}&lang=tr",
        )

    def get_progress(self):
        data = self._safe_post(
            "progress",
            f"with_lastacts=0&ses={self.session}&lang=tr",
        )
        return data.get("progress", [])

    def get_lastacts(self):
        data = self._safe_post(
            "progress",
            f"with_lastacts=1&ses={self.session}&lang=tr",
        )
        return data.get("lastacts", [])

    def set_client(self, clientid):
        return self._safe_post(
            "logs",
            f"filter={clientid}&ll=0&ses={self.session}&lang=tr",
        )

    def get_log(self, clientid, logid):
        self.set_client(clientid)
        data = self._safe_post(
            "logs",
            f"logid={logid}&ses={self.session}&lang=tr",
        )
        return data.get("log", {}).get("data", "")
