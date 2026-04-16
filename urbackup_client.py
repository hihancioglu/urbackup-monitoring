from urbackup_api import UrBackupAPI


class UrBackupClient(UrBackupAPI):
    """Backward-compatible wrapper."""

    def __init__(self, base, username, password):
        super().__init__(base_url=base, username=username, password=password)

    def get_usage(self):
        return self.usage()

    def get_status(self):
        return self.status()

    def get_progress(self):
        return self.progress()

    def set_client(self, clientid):
        return self.logs(client_id=clientid)

    def get_log(self, clientid, logid):
        self.set_client(clientid)
        data = self.logs(log_id=logid)
        return data.get("log", {}).get("data", "")
