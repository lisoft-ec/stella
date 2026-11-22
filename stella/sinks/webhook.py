"""Outgoing webhook: POST each event as JSON to a configurable URL."""
import requests


class WebhookSink:
    name = "webhook"

    def __init__(self, config):
        self.config = config

    def enabled(self):
        cfg = self.config.section("webhook")
        return bool(cfg["enabled"] and cfg["url"])

    def ready(self):
        return True

    def send(self, event, cfg=None):
        cfg = cfg or self.config.section("webhook")
        headers = {"Content-Type": "application/json"}
        headers.update({str(k): str(v) for k, v in (cfg.get("headers") or {}).items()})
        resp = requests.post(cfg["url"], json=event, headers=headers, timeout=float(cfg.get("timeout", 5)))
        resp.raise_for_status()
        return resp.status_code

    def test(self, cfg, device_id):
        """Send a test payload with the given (possibly unsaved) settings."""
        try:
            code = self.send({"test": True, "device_id": device_id}, cfg)
        except Exception as exc:
            return False, str(exc)
        return True, "HTTP %s" % code
