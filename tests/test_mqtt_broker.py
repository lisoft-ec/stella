"""MQTT against a real broker. Run with STELLA_TEST_MQTT=host:port, e.g.

    docker run --rm -d -p 1883:1883 eclipse-mosquitto:2 mosquitto -c /mosquitto-no-auth.conf
    STELLA_TEST_MQTT=localhost:1883 pytest tests/test_mqtt_broker.py
"""
import json
import os
import threading
import time

import paho.mqtt.client as mqtt
import pytest

from stella.config import Config
from stella.sinks.mqtt import MqttSink

BROKER = os.environ.get("STELLA_TEST_MQTT")
pytestmark = pytest.mark.skipif(not BROKER, reason="STELLA_TEST_MQTT no definido")


def wait_for(predicate, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        if predicate():
            return True
        time.sleep(0.05)
    return False


def test_end_to_end_with_broker(tmp_path):
    host, port = BROKER.split(":")
    config = Config(str(tmp_path / "config.yaml")).load()
    config.update_section("device", {"id": "test-%d" % os.getpid()})
    config.update_section("mqtt", {"enabled": True, "host": host, "port": int(port)})
    device_id = config.get("device.id")

    received = {}
    observer = mqtt.Client(client_id="observer-%d" % os.getpid())
    observer.on_message = lambda c, u, m: received.setdefault(m.topic, []).append(m.payload)
    observer.connect(host, int(port))
    observer.subscribe("stella/%s/#" % device_id)
    observer.subscribe("homeassistant/+/%s/#" % device_id)
    observer.loop_start()

    commands = []
    sink = MqttSink(config, on_command=lambda c, a: commands.append(c))
    sink.start()
    try:
        assert wait_for(sink.ready), "no conectó al broker"
        assert MqttSink.test(config.section("mqtt"), device_id)[0]
        sink.send({"uid": "u1", "direction": "in"})
        sink.publish_counters({"in": 1, "out": 0, "occupancy": 1})
        observer.publish("stella/%s/cmd" % device_id, "reset_counters", qos=1)
        assert wait_for(lambda: commands == ["reset_counters"])
        assert wait_for(lambda: "stella/%s/event" % device_id in received)
        assert json.loads(received["stella/%s/event" % device_id][0])["uid"] == "u1"
        assert received["stella/%s/availability" % device_id][0] == b"online"
        assert wait_for(lambda: "homeassistant/sensor/%s/entries/config" % device_id in received)
    finally:
        sink.stop()
        assert wait_for(lambda: received["stella/%s/availability" % device_id][-1] == b"offline")
        # Clean retained messages.
        for topic in list(received):
            observer.publish(topic, b"", retain=True)
        time.sleep(0.3)
        observer.loop_stop()
        observer.disconnect()
