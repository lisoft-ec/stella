"""MQTT client: events, counters, status, commands and Home Assistant discovery.

Topics (``<p>`` = ``mqtt.topic_prefix``, ``<id>`` = ``device.id``):

- ``<p>/<id>/event``         one JSON message per crossing (QoS 1)
- ``<p>/<id>/counters``      daily totals and occupancy (retained)
- ``<p>/<id>/status``        periodic heartbeat (retained)
- ``<p>/<id>/availability``  ``online`` / ``offline`` (retained, last will)
- ``<p>/<id>/cmd``           commands: ``reset_counters``, ``restart``
"""
import json
import logging
import threading

import paho.mqtt.client as mqtt

from .. import __version__

log = logging.getLogger(__name__)

COMMANDS = ("reset_counters", "restart")


def parse_command(payload):
    """Accept ``reset_counters`` or ``{"command": "reset_counters", ...}``."""
    text = payload.decode("utf-8", "replace").strip() if isinstance(payload, bytes) else str(payload).strip()
    args = {}
    if text.startswith("{"):
        try:
            data = json.loads(text)
        except ValueError:
            return None, {}
        text = str(data.pop("command", ""))
        args = data
    return (text, args) if text in COMMANDS else (None, {})


class MqttSink:
    name = "mqtt"

    def __init__(self, config, on_command=None):
        self.config = config
        self.on_command = on_command
        self.client = None
        self.connected = False
        self._lock = threading.Lock()
        self._last_counters = None

    # -- topics -----------------------------------------------------------
    def topic(self, leaf, cfg=None, device_id=None):
        cfg = cfg or self.config.section("mqtt")
        device_id = device_id or self.config.get("device.id")
        return "%s/%s/%s" % (cfg["topic_prefix"], device_id, leaf)

    # -- lifecycle --------------------------------------------------------
    def enabled(self):
        return bool(self.config.get("mqtt.enabled"))

    def ready(self):
        return self.connected

    @staticmethod
    def _make_client(cfg, device_id):
        client = mqtt.Client(client_id="stella-%s" % device_id, clean_session=True)
        if cfg.get("username"):
            client.username_pw_set(cfg["username"], cfg.get("password") or None)
        client.reconnect_delay_set(1, 60)
        return client

    def start(self):
        with self._lock:
            if self.client is not None or not self.enabled():
                return
            cfg = self.config.section("mqtt")
            device_id = self.config.get("device.id")
            client = self._make_client(cfg, device_id)
            client.will_set(self.topic("availability", cfg, device_id), "offline", qos=1, retain=True)
            client.on_connect = self._on_connect
            client.on_disconnect = self._on_disconnect
            client.on_message = self._on_message
            client.connect_async(cfg["host"], cfg["port"], int(cfg.get("keepalive", 60)))
            client.loop_start()
            self.client = client
            log.info("MQTT connecting to %s:%s", cfg["host"], cfg["port"])

    def stop(self):
        with self._lock:
            client, self.client = self.client, None
            self.connected = False
        if client is not None:
            try:
                info = client.publish(self.topic("availability"), "offline", qos=1, retain=True)
                info.wait_for_publish(2)
            except Exception:
                pass
            client.disconnect()
            client.loop_stop()

    def restart(self):
        self.stop()
        self.start()

    # -- callbacks ----------------------------------------------------------
    def _on_connect(self, client, userdata, flags, rc):
        if rc != 0:
            log.warning("MQTT connection refused: %s", mqtt.connack_string(rc))
            return
        log.info("MQTT connected")
        self.connected = True
        client.publish(self.topic("availability"), "online", qos=1, retain=True)
        client.subscribe(self.topic("cmd"), qos=1)
        if self.config.get("mqtt.homeassistant"):
            self.publish_discovery(client)
        if self._last_counters is not None:
            self.publish_counters(self._last_counters)

    def _on_disconnect(self, client, userdata, rc):
        self.connected = False
        if rc != 0:
            log.warning("MQTT disconnected unexpectedly (%s)", rc)

    def _on_message(self, client, userdata, msg):
        command, args = parse_command(msg.payload)
        if command is None:
            log.warning("Unknown MQTT command on %s: %r", msg.topic, msg.payload[:100])
            return
        log.info("MQTT command: %s", command)
        if self.on_command is not None:
            try:
                self.on_command(command, args)
            except Exception:
                log.exception("MQTT command %s failed", command)

    # -- publishing -----------------------------------------------------------
    def send(self, event):
        """Outbox delivery: QoS 1 and wait for the broker's ack."""
        client = self.client
        if client is None or not self.connected:
            raise RuntimeError("MQTT no conectado")
        info = client.publish(self.topic("event"), json.dumps(event), qos=1)
        info.wait_for_publish(10)
        if not info.is_published():
            raise RuntimeError("MQTT: el broker no confirmó la publicación")

    def publish_counters(self, counters):
        self._last_counters = counters
        client = self.client
        if client is not None and self.connected:
            client.publish(self.topic("counters"), json.dumps(counters), qos=1, retain=True)

    def publish_status(self, status):
        client = self.client
        if client is not None and self.connected:
            client.publish(self.topic("status"), json.dumps(status), qos=0, retain=True)

    def discovery_messages(self):
        """(topic, payload) pairs for Home Assistant MQTT discovery."""
        cfg = self.config.section("mqtt")
        device_id = self.config.get("device.id")
        name = self.config.get("device.name") or "Stella"
        prefix = cfg["discovery_prefix"].strip("/")
        device = {
            "identifiers": [device_id],
            "name": "%s (%s)" % (name, device_id),
            "manufacturer": "Stella",
            "model": "Coral Dev Board",
            "sw_version": __version__,
        }
        availability = self.topic("availability", cfg, device_id)
        sensors = [
            ("entries", "Entradas hoy", "counters", "{{ value_json['in'] }}", {"state_class": "total_increasing", "icon": "mdi:login"}),
            ("exits", "Salidas hoy", "counters", "{{ value_json['out'] }}", {"state_class": "total_increasing", "icon": "mdi:logout"}),
            ("occupancy", "Aforo", "counters", "{{ value_json['occupancy'] }}", {"state_class": "measurement", "icon": "mdi:account-group"}),
            ("temperature", "Temperatura", "status", "{{ value_json['temperature'] }}",
             {"device_class": "temperature", "unit_of_measurement": "°C", "state_class": "measurement",
              "entity_category": "diagnostic"}),
        ]
        messages = []
        for key, title, leaf, template, extra in sensors:
            payload = {
                "name": title,
                "unique_id": "%s_%s" % (device_id, key),
                "state_topic": self.topic(leaf, cfg, device_id),
                "value_template": template,
                "availability_topic": availability,
                "device": device,
            }
            payload.update(extra)
            messages.append(("%s/sensor/%s/%s/config" % (prefix, device_id, key), payload))
        messages.append(("%s/button/%s/reset/config" % (prefix, device_id), {
            "name": "Reiniciar contadores",
            "unique_id": "%s_reset" % device_id,
            "command_topic": self.topic("cmd", cfg, device_id),
            "payload_press": "reset_counters",
            "availability_topic": availability,
            "device": device,
            "icon": "mdi:counter",
        }))
        return messages

    def publish_discovery(self, client=None):
        client = client or self.client
        for topic, payload in self.discovery_messages():
            client.publish(topic, json.dumps(payload), qos=1, retain=True)

    # -- connection test ------------------------------------------------------
    @classmethod
    def test(cls, cfg, device_id, timeout=5.0):
        """Try to connect with the given (possibly unsaved) settings."""
        done = threading.Event()
        result = {"rc": None}

        def on_connect(client, userdata, flags, rc):
            result["rc"] = rc
            done.set()

        client = cls._make_client(cfg, device_id + "-test")
        client.on_connect = on_connect
        try:
            client.connect(cfg["host"], int(cfg["port"]), 10)
        except Exception as exc:
            return False, "No se pudo conectar: %s" % exc
        client.loop_start()
        done.wait(timeout)
        client.disconnect()
        client.loop_stop()
        if result["rc"] is None:
            return False, "Sin respuesta del broker"
        if result["rc"] != 0:
            return False, mqtt.connack_string(result["rc"])
        return True, "Conectado"
