"""Application wiring: pipeline, counters, storage, sinks and web server."""
import datetime
import logging
import os
import threading
import time
import uuid

from . import __version__
from .counters import Counters
from .hw import system
from .hw.leds import Leds
from .logbuffer import LogBuffer
from .net.wifi import Network
from .ota import Ota
from .outbox import Outbox
from .pipeline import Pipeline
from .sinks.mqtt import MqttSink
from .sinks.webhook import WebhookSink
from .storage import Storage

log = logging.getLogger(__name__)

PIPELINE_SECTIONS = ("camera", "detector", "motion", "tracking", "counting", "web")


class App:
    def __init__(self, config, detector=None, start_pipeline=True):
        self.config = config
        self.logs = LogBuffer()
        logging.getLogger().addHandler(self.logs)
        system.apply_timezone(config.get("device.timezone"))

        self.storage = Storage(os.path.join(config.data_dir, "events.db"))
        self.counters = Counters(self.storage, config)
        self.mqtt = MqttSink(config, on_command=self.handle_command)
        self.webhook = WebhookSink(config)
        self.outbox = Outbox(self.storage, [self.mqtt, self.webhook])
        self.pipeline = Pipeline(config, on_event=self.on_crossing, detector=detector)
        self.leds = Leds(config)
        self.network = Network(config, self.storage)
        self.ota = Ota(config)
        self._start_pipeline = start_pipeline
        self._stop = threading.Event()
        self._event_seq = 0
        self._last_event = None
        self._event_cond = threading.Condition()
        config.on_change(self._on_config_change)

    # -- events -------------------------------------------------------------
    def on_crossing(self, direction, track):
        state = self.counters.apply(direction)
        event = {
            "uid": uuid.uuid4().hex,
            "device_id": self.config.get("device.id"),
            "ts": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
            "direction": direction,
            "track_id": track.id,
            "counters": {k: state[k] for k in ("day", "in", "out", "occupancy")},
            "version": __version__,
        }
        event["id"] = self.outbox.enqueue(event)
        self.mqtt.publish_counters(state)
        with self._event_cond:
            self._event_seq += 1
            self._last_event = event
            self._event_cond.notify_all()
        self.on_event_hook(event, state)
        return event

    def on_event_hook(self, event, state):
        self.leds.flash("entry" if event["direction"] == "in" else "exit")

    def reset_counters(self, occupancy=0):
        state = self.counters.reset(occupancy)
        log.info("Counters reset (occupancy=%s)", occupancy)
        self.mqtt.publish_counters(state)
        return state

    def handle_command(self, command, args=None):
        args = args or {}
        if command == "reset_counters":
            return self.reset_counters(int(args.get("occupancy", 0) or 0))
        if command == "restart":
            return system.restart_service(self.config.get("ota.service", "stella"))
        raise ValueError("Comando desconocido: %s" % command)

    def last_event(self):
        with self._event_cond:
            return self._event_seq, self._last_event

    # -- status -------------------------------------------------------------
    def status(self):
        snap = self.pipeline.snapshot()
        snap.pop("tracks", None)
        return {
            "device": {"id": self.config.get("device.id"), "name": self.config.get("device.name")},
            "version": __version__,
            "time": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
            "timezone": self.config.get("device.timezone"),
            "uptime": system.process_uptime(),
            "system_uptime": system.system_uptime(),
            "temperature": system.temperature(),
            "ips": system.ip_addresses(),
            "pipeline": snap,
            "counters": self.counters.state(),
            "mqtt": {"enabled": self.mqtt.enabled(), "connected": self.mqtt.connected},
            "webhook": {"enabled": self.webhook.enabled()},
            "pending_deliveries": self.storage.pending_count(),
            "default_password": bool(self.config.get("web.default_password")),
        }

    def heartbeat(self):
        status = self.status()
        return {
            "version": status["version"],
            "time": status["time"],
            "uptime": status["uptime"],
            "temperature": status["temperature"],
            "ips": status["ips"],
            "fps": status["pipeline"]["fps"],
            "inference_ms": status["pipeline"]["inference_ms"],
            "pipeline_error": status["pipeline"]["error"],
            "pending_deliveries": status["pending_deliveries"],
        }

    # -- config changes -------------------------------------------------------
    def _on_config_change(self, section):
        if section in PIPELINE_SECTIONS:
            self.pipeline.request_reload(section)
        if section in ("mqtt", "device"):
            threading.Thread(target=self.mqtt.restart, name="mqtt-restart", daemon=True).start()
        if section == "device":
            system.apply_timezone(self.config.get("device.timezone"))
        if section == "counting":
            self.mqtt.publish_counters(self.counters.state())
        if section == "leds":
            self.leds.reconfigure()
        if section == "network":
            threading.Thread(target=self.network.apply_safe, name="network-apply", daemon=True).start()

    # -- background housekeeping ----------------------------------------------
    def _housekeeping(self):
        last_status = 0.0
        last_prune = 0.0
        while not self._stop.wait(1.0):
            try:
                if self.counters.check_rollover():
                    log.info("New business day: counters reset")
                    self.mqtt.publish_counters(self.counters.state())
                now = time.monotonic()
                if now - last_status >= self.config.get("mqtt.status_interval", 60):
                    last_status = now
                    self.mqtt.publish_status(self.heartbeat())
                if now - last_prune >= 86400 or not last_prune:
                    last_prune = now
                    self.storage.prune()
                self.tick()
            except Exception:
                log.exception("Housekeeping failed")

    def tick(self):
        """Called every second: confirm a pending OTA, update the LED conditions."""
        if system.process_uptime() >= self.config.get("ota.healthy_after", 60) and self.ota.pending():
            self.ota.mark_healthy()
        snap = self.pipeline.snapshot()
        self.leds.set_condition("error", bool(snap["error"]) and not self.pipeline.finished)
        self.leds.set_condition("full", self.counters.state()["full"])
        if self.network.managed():
            # Refreshed every 10 s by the network monitor thread (no extra nmcli call here).
            st = self.network.last_status
            self.leds.set_condition("hotspot", bool(st.get("hotspot_active")))
            self.leds.set_condition("no_network", st.get("connected") is False and not st.get("hotspot_active"))
        else:
            self.leds.set_condition("hotspot", False)
            self.leds.set_condition("no_network", False)

    # -- lifecycle ----------------------------------------------------------
    def start(self):
        self.mqtt.publish_counters(self.counters.state())
        self.leds.start()
        self.network.start()
        self.mqtt.start()
        self.outbox.start()
        if self._start_pipeline:
            self.pipeline.start()
        threading.Thread(target=self._housekeeping, name="housekeeping", daemon=True).start()
        return self

    def factory_reset(self, restart=True):
        """Forget Wi-Fi, data and configuration, then restart (see stella/factory.py)."""
        from .factory import factory_reset

        service = self.config.get("ota.service", "stella")
        summary = factory_reset(self.config, self.network, release=self.stop)
        if restart:
            system.restart_service(service)
        return summary

    def stop(self):
        if self._stop.is_set():
            return
        self._stop.set()
        self.network.stop()
        self.leds.stop()
        self.pipeline.stop()
        self.outbox.stop()
        self.mqtt.stop()
        self.storage.close()

    def run(self):
        from waitress import serve

        from .web import create_app

        self.start()
        web = self.config.section("web")
        log.info("Web interface on http://%s:%s", web["host"], web["port"])
        try:
            serve(create_app(self), host=web["host"], port=int(web["port"]), threads=16,
                  ident="Stella", channel_timeout=300)
        finally:
            self.stop()
