import pytest

from stella.config import Config
from stella.hw.leds import OFF, Leds
from stella.net.wifi import HOTSPOT, Network, NmcliError, split_terse
from stella.storage import Storage


@pytest.fixture
def config(tmp_path):
    cfg = Config(str(tmp_path / "config.yaml")).load()
    cfg.update_section("leds", {"driver": "none"})
    return cfg


@pytest.fixture
def storage(tmp_path):
    s = Storage(str(tmp_path / "events.db"))
    yield s
    s.close()


# -- LEDs -------------------------------------------------------------------
def test_led_priorities_and_flash(config):
    leds = Leds(config)
    colors = config.get("leds.colors")
    assert leds.desired() == OFF
    leds.set_condition("no_network", True)
    assert leds.desired() == tuple(colors["no_network"])
    leds.set_condition("error", True)
    assert leds.desired() == tuple(colors["error"])
    leds.flash("entry")
    assert leds.desired() == tuple(colors["entry"])
    assert leds.desired(now=10 ** 9) == tuple(colors["error"])  # flash expired
    leds.set_condition("error", False)
    leds.set_condition("no_network", False)
    assert leds.desired(now=10 ** 9) == OFF


def test_gpio_driver_falls_back_without_hardware(config):
    config.update_section("leds", {"driver": "gpio", "pins": {"red": 9990, "green": 9991, "blue": 9992}})
    leds = Leds(config)  # no /sys/class/gpio on the PC: must not raise
    leds.tick()


# -- nmcli parsing --------------------------------------------------------------
def test_split_terse_handles_escaped_colons():
    assert split_terse(r"Mi\:Red:80:WPA2") == ["Mi:Red", "80", "WPA2"]


class FakeNmcli:
    """Minimal NetworkManager model driven by the nmcli arguments."""

    def __init__(self):
        self.calls = []
        self.connections = {"Wired connection 1": "802-3-ethernet", "gadget0": "802-3-ethernet"}
        self.active = {}  # device -> connection
        self.wifi_available = []
        self.fail_up = set()

    def __call__(self, *args):
        self.calls.append(args)
        if args[:3] == ("-t", "-f", "NAME,TYPE,DEVICE"):
            return "".join("%s:%s:\n" % (n, t) for n, t in self.connections.items())
        if args[:3] == ("-t", "-f", "DEVICE,TYPE,STATE,CONNECTION"):
            lines = []
            wlan = self.active.get("wlan0")
            lines.append("wlan0:wifi:%s:%s" % ("connected" if wlan else "disconnected", wlan or ""))
            eth = self.active.get("eth0")
            lines.append("eth0:ethernet:%s:%s" % ("connected" if eth else "unavailable", eth or ""))
            lines.append("usb0:ethernet:connected:gadget0")
            return "\n".join(lines) + "\n"
        if args[:3] == ("-t", "-f", "SSID,SIGNAL,SECURITY"):
            return "Casa:70:WPA2\nCasa:40:WPA2\nVecino:55:\n"
        if args[:2] == ("connection", "add"):
            name = args[args.index("con-name") + 1]
            self.connections[name] = "802-11-wireless"
            return ""
        if args[:2] == ("connection", "delete"):
            self.connections.pop(args[2], None)
            return ""
        if args[:2] == ("connection", "up"):
            if args[2] in self.fail_up:
                raise NmcliError("no se puede activar")
            if args[2] == HOTSPOT:
                self.active["wlan0"] = HOTSPOT
            return ""
        if args[:2] == ("connection", "down"):
            if self.active.get("wlan0") == args[2]:
                del self.active["wlan0"]
            return ""
        return ""

    def names(self, verb):
        return [c[2] if verb != "add" else c[c.index("con-name") + 1]
                for c in self.calls if c[:2] == ("connection", verb)]


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def network(config, storage, nm=None, clock=None):
    config.update_section("network", {"managed": True}, notify=False)
    return Network(config, storage, runner=nm or FakeNmcli(), clock=clock or Clock())


def test_apply_creates_only_changed_connections(config, storage):
    nm = FakeNmcli()
    net = network(config, storage, nm)
    config.update_section("network", {"wifi": [{"ssid": "Casa", "password": "clave-casa", "priority": 5},
                                               {"ssid": "Abierta", "password": ""}]}, notify=False)
    net.apply()
    assert sorted(nm.names("add")) == [HOTSPOT, "stella-wifi-Abierta", "stella-wifi-Casa"]
    casa = [c for c in nm.calls if c[:2] == ("connection", "add") and "stella-wifi-Casa" in c][0]
    assert "wifi-sec.psk" in casa and "clave-casa" in casa
    abierta = [c for c in nm.calls if c[:2] == ("connection", "add") and "stella-wifi-Abierta" in c][0]
    assert "wifi-sec.psk" not in abierta
    # Ethernet (not the USB gadget) set to DHCP.
    assert any(c[:3] == ("connection", "modify", "Wired connection 1") for c in nm.calls)
    assert not any("gadget0" in c for c in nm.calls if c[:2] == ("connection", "modify"))

    nm.calls.clear()
    net.apply()  # nothing changed
    assert nm.names("add") == [] and nm.names("delete") == []

    config.update_section("network", {"wifi": [{"ssid": "Casa", "password": "otra-clave", "priority": 5}]},
                          notify=False)
    nm.calls.clear()
    net.apply()
    assert nm.names("add") == ["stella-wifi-Casa"]
    assert sorted(nm.names("delete")) == ["stella-wifi-Abierta", "stella-wifi-Casa"]


def test_status_reports_ips_and_hostname(config, storage):
    nm = FakeNmcli()
    net = network(config, storage, nm)
    st = net.status()
    assert st["connected"] is False  # the USB gadget does not count
    assert st["hostname"]
    nm.active["wlan0"] = "stella-wifi-Casa"
    assert net.status()["connected"] is True

def test_unmanaged_network_does_nothing(config, storage):
    nm = FakeNmcli()
    net = Network(config, storage, runner=nm)
    net.apply()
    net.check()
    assert nm.calls == []
    assert net.status()["managed"] is False


def test_hotspot_after_timeout_and_retry(config, storage, monkeypatch):
    nm, clock = FakeNmcli(), Clock()
    net = network(config, storage, nm, clock)
    config.update_section("network", {"wifi": [{"ssid": "Casa", "password": "clave-casa"}],
                                      "hotspot": {"timeout": 60, "retry_interval": 300}}, notify=False)
    nm.connections["stella-wifi-Casa"] = "802-11-wireless"  # as created by apply()
    net.check()                      # first time without connection
    clock.t += 30
    net.check()
    assert nm.active.get("wlan0") is None
    clock.t += 31
    net.check()                      # > timeout: hotspot up
    assert nm.active["wlan0"] == HOTSPOT

    # Retry: someone is using the web, so the hotspot stays.
    clock.t += 301
    net.touch_web()
    net.check()
    assert nm.active["wlan0"] == HOTSPOT

    # Web quiet: leaves the hotspot; the known network connects.
    clock.t += 200

    def fake_wait(seconds):
        nm.active["wlan0"] = "stella-wifi-Casa"
        clock.t += seconds
        return False
    monkeypatch.setattr(net._stop, "wait", fake_wait)
    net.check()
    assert nm.active["wlan0"] == "stella-wifi-Casa"


def test_hotspot_dropped_when_ethernet_connects(config, storage):
    nm = FakeNmcli()
    net = network(config, storage, nm)
    nm.active["wlan0"] = HOTSPOT
    nm.active["eth0"] = "Wired connection 1"
    net.check()
    assert "wlan0" not in nm.active


def test_led_preview_wins_and_expires(config):
    leds = Leds(config)
    leds.set_condition("error", True)
    leds.flash("entry")
    leds.preview([1, 1, 1], seconds=5)
    assert leds.desired() == (1, 1, 1)
    assert leds.desired(now=10 ** 9) == tuple(config.get("leds.colors")["error"])
    assert leds.driver == "none"


def test_hotspot_retries_networks_created_outside_stella(config, storage, monkeypatch):
    nm, clock = FakeNmcli(), Clock()
    nm.connections["WIFI-IOT"] = "802-11-wireless"   # not in Stella's YAML
    net = network(config, storage, nm, clock)
    config.update_section("network", {"hotspot": {"timeout": 30, "retry_interval": 60}}, notify=False)
    nm.active["wlan0"] = HOTSPOT
    net.check()
    clock.t += 61

    def fake_wait(seconds):
        nm.active["wlan0"] = "WIFI-IOT"
        clock.t += seconds
        return False
    monkeypatch.setattr(net._stop, "wait", fake_wait)
    net.check()
    assert nm.active["wlan0"] == "WIFI-IOT"


def test_no_retry_without_any_wifi(config, storage):
    nm, clock = FakeNmcli(), Clock()
    net = network(config, storage, nm, clock)
    nm.active["wlan0"] = HOTSPOT
    net.check()
    clock.t += 10 ** 6
    net.check()
    assert nm.active["wlan0"] == HOTSPOT
    assert not any(c[:2] == ("connection", "down") for c in nm.calls)


def test_delete_all_wifi_keeps_usb_and_ethernet(config, storage):
    nm = FakeNmcli()
    nm.connections.update({"WIFI-IOT": "802-11-wireless", "stella-wifi-Casa": "802-11-wireless",
                           HOTSPOT: "802-11-wireless"})
    net = network(config, storage, nm)
    removed = net.delete_all_wifi()
    assert sorted(removed) == sorted(["WIFI-IOT", "stella-wifi-Casa", HOTSPOT])
    assert set(nm.connections) == {"Wired connection 1", "gadget0"}


def test_status_is_cached_for_the_leds(config, storage):
    nm = FakeNmcli()
    net = network(config, storage, nm)
    assert net.last_status == {}
    net.check()
    assert net.last_status["managed"] is True


def test_nmcli_runs_without_sudo_by_default(config, storage):
    net = Network(config, storage)
    assert net.nmcli.use_sudo is False


def test_hidden_network_is_configured_as_hidden(config, storage):
    nm = FakeNmcli()
    net = network(config, storage, nm)
    config.update_section("network", {"wifi": [{"ssid": "Oculta", "password": "clave-oculta", "hidden": True},
                                               {"ssid": "Visible", "password": ""}]}, notify=False)
    net.apply()
    adds = {c[c.index("con-name") + 1]: c for c in nm.calls if c[:2] == ("connection", "add")}
    oculta = adds["stella-wifi-Oculta"]
    assert oculta[oculta.index("802-11-wireless.hidden") + 1] == "yes"
    assert "802-11-wireless.hidden" not in adds["stella-wifi-Visible"]
    assert config.get("network.wifi")[1]["hidden"] is False
