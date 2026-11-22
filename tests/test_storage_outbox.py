import datetime
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from stella.config import Config
from stella.counters import Counters, business_day
from stella.outbox import Outbox
from stella.sinks.mqtt import MqttSink, parse_command
from stella.sinks.webhook import WebhookSink
from stella.storage import Storage


@pytest.fixture
def config(tmp_path):
    return Config(str(tmp_path / "config.yaml")).load()


@pytest.fixture
def storage(tmp_path):
    s = Storage(str(tmp_path / "events.db"))
    yield s
    s.close()


def event(uid, direction="in"):
    return {"uid": uid, "ts": "2026-11-21T10:00:00-05:00", "direction": direction}


class FakeSink:
    def __init__(self, name, fail=0):
        self.name = name
        self.fail = fail
        self.sent = []
        self.on = True

    def enabled(self):
        return self.on

    def ready(self):
        return True

    def send(self, ev):
        if self.fail:
            self.fail -= 1
            raise RuntimeError("caído")
        self.sent.append(ev["uid"])


def test_storage_events_and_kv(storage):
    storage.add_event(event("a"), ["mqtt"])
    storage.add_event(event("b", "out"), [])
    rows = storage.events()
    assert [r["uid"] for r in rows] == ["b", "a"]
    assert storage.events(since_id=rows[1]["id"])[0]["uid"] == "b"
    storage.set("x", {"n": 1})
    assert storage.get("x") == {"n": 1}
    assert storage.get("missing", 5) == 5


def test_outbox_delivers_in_order_and_retries(storage):
    good, flaky = FakeSink("good"), FakeSink("flaky", fail=1)
    outbox = Outbox(storage, [good, flaky])
    for uid in ("e1", "e2", "e3"):
        outbox.enqueue(event(uid))
    assert outbox.flush_once() == 3
    assert good.sent == ["e1", "e2", "e3"]
    # flaky failed on e1 and stopped (order kept); retry is scheduled later.
    assert flaky.sent == []
    assert storage.pending_count("flaky") == 3
    # Force the retry time to now.
    for event_id, _, _ in storage.pending("flaky", now=10 ** 12):
        storage._db.execute("UPDATE deliveries SET next_try = 0 WHERE event_id = ?", (event_id,))
    outbox.flush_once()
    assert flaky.sent == ["e1", "e2", "e3"]
    assert storage.pending_count() == 0
    # Already delivered: nothing is sent twice.
    assert outbox.flush_once() == 0


def test_disabled_sink_gets_no_deliveries(storage):
    sink = FakeSink("off")
    sink.on = False
    outbox = Outbox(storage, [sink])
    outbox.enqueue(event("x"))
    assert storage.pending_count("off") == 0


def test_business_day_and_rollover(config, storage):
    assert business_day(datetime.datetime(2026, 11, 21, 5, 0), "06:00") == "2026-11-20"
    assert business_day(datetime.datetime(2026, 11, 21, 6, 0), "06:00") == "2026-11-21"

    now = [datetime.datetime(2026, 11, 21, 12, 0)]
    counters = Counters(storage, config, clock=lambda: now[0])
    counters.apply("in")
    counters.apply("in")
    state = counters.apply("out")
    assert (state["in"], state["out"], state["occupancy"]) == (2, 1, 1)
    counters.apply("out")
    assert counters.apply("out")["occupancy"] == 0  # never negative

    # Persisted across restarts.
    again = Counters(storage, config, clock=lambda: now[0])
    assert again.state()["in"] == 2

    now[0] = datetime.datetime(2026, 11, 22, 0, 1)
    assert again.check_rollover() is True
    assert again.state()["in"] == 0


def test_occupancy_limit(config, storage):
    config.update_section("counting", {"occupancy_limit": 2})
    counters = Counters(storage, config)
    counters.apply("in")
    assert counters.state()["full"] is False
    assert counters.apply("in")["full"] is True


class _Handler(BaseHTTPRequestHandler):
    received = []

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        _Handler.received.append((self.headers.get("X-Token"), json.loads(body)))
        self.send_response(204 if self.path == "/ok" else 500)
        self.end_headers()

    def log_message(self, *args):
        pass


@pytest.fixture
def http_server():
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    _Handler.received = []
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield "http://127.0.0.1:%d" % server.server_port
    server.shutdown()


def test_webhook_sink(config, http_server):
    config.update_section("webhook", {"enabled": True, "url": http_server + "/ok", "headers": {"X-Token": "t"}})
    sink = WebhookSink(config)
    assert sink.enabled()
    sink.send(event("w1"))
    assert _Handler.received == [("t", event("w1"))]
    ok, msg = sink.test(dict(config.section("webhook"), url=http_server + "/fail"), "dev")
    assert ok is False and "500" in msg


def test_mqtt_command_parsing():
    assert parse_command(b"reset_counters") == ("reset_counters", {})
    assert parse_command(b'{"command": "restart", "delay": 2}') == ("restart", {"delay": 2})
    assert parse_command(b"rm -rf") == (None, {})
    assert parse_command(b"{bad json") == (None, {})


def test_mqtt_topics_and_discovery(config):
    config.update_section("mqtt", {"topic_prefix": "aforo/", "homeassistant": True})
    config.update_section("device", {"id": "puerta-1"})
    sink = MqttSink(config)
    assert sink.topic("event") == "aforo/puerta-1/event"
    msgs = dict(sink.discovery_messages())
    entries = msgs["homeassistant/sensor/puerta-1/entries/config"]
    assert entries["state_topic"] == "aforo/puerta-1/counters"
    assert entries["availability_topic"] == "aforo/puerta-1/availability"
    button = msgs["homeassistant/button/puerta-1/reset/config"]
    assert button["command_topic"] == "aforo/puerta-1/cmd"
    assert button["payload_press"] == "reset_counters"


def test_mqtt_send_requires_connection(config):
    with pytest.raises(RuntimeError):
        MqttSink(config).send(event("m1"))
