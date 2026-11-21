"""Network configuration through NetworkManager (``nmcli``).

Stella owns the connections named ``stella-wifi-<ssid>`` and
``stella-hotspot`` and, for Ethernet, the existing wired connection. The
USB gadget connections of the Coral board are never touched.

A monitor thread starts the hotspot when there is no connection for
``hotspot.timeout`` seconds and periodically leaves it to retry the known
networks (unless someone used the web interface recently).
"""
import hashlib
import json
import logging
import re
import subprocess
import threading
import time

log = logging.getLogger(__name__)

WIFI_PREFIX = "stella-wifi-"
HOTSPOT = "stella-hotspot"
APPLIED_KEY = "network_applied"
WEB_QUIET = 120  # seconds of web inactivity before leaving the hotspot to retry


class NmcliError(RuntimeError):
    pass


def split_terse(line):
    """Split a ``nmcli -t`` line on unescaped colons and unescape the fields."""
    fields = re.split(r"(?<!\\):", line)
    return [f.replace("\\:", ":").replace("\\\\", "\\") for f in fields]


class Nmcli:
    def __init__(self, use_sudo=True, timeout=45):
        self.use_sudo = use_sudo
        self.timeout = timeout

    def __call__(self, *args):
        cmd = (["sudo", "-n"] if self.use_sudo else []) + ["nmcli"] + [str(a) for a in args]
        try:
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  universal_newlines=True, timeout=self.timeout)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise NmcliError(str(exc))
        if proc.returncode != 0:
            raise NmcliError((proc.stderr or proc.stdout).strip() or "nmcli falló (%s)" % proc.returncode)
        return proc.stdout


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()[:16]


class Network:
    def __init__(self, config, storage, runner=None, clock=time.monotonic):
        self.config = config
        self.storage = storage
        self._runner = runner
        self._clock = clock
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread = None
        self._no_conn_since = None
        self._hotspot_since = None
        self._last_web = 0.0
        self.last_error = None

    # -- helpers ------------------------------------------------------------
    @property
    def nmcli(self):
        if self._runner is None:
            self._runner = Nmcli(self.config.get("network.use_sudo", True))
        return self._runner

    def managed(self):
        return bool(self.config.get("network.managed"))

    def touch_web(self):
        """Called on every web request: do not drop the hotspot under a user."""
        self._last_web = self._clock()

    def interface(self):
        return self.config.get("network.interface", "wlan0")

    # -- read-only queries ----------------------------------------------------
    def devices(self):
        out = self.nmcli("-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device")
        result = []
        for line in out.splitlines():
            parts = split_terse(line)
            if len(parts) < 4 or parts[1] in ("loopback", "bridge", "tun") or parts[0].startswith("p2p"):
                continue
            result.append({"device": parts[0], "type": parts[1], "state": parts[2], "connection": parts[3]})
        return result

    def connections(self):
        out = self.nmcli("-t", "-f", "NAME,TYPE,DEVICE", "connection", "show")
        return [dict(zip(("name", "type", "device"), split_terse(l))) for l in out.splitlines() if l]

    def status(self):
        if not self.managed():
            return {"managed": False, "connected": None, "hotspot_active": False, "devices": []}
        devices = self.devices()
        hotspot = any(d["connection"] == HOTSPOT for d in devices)
        connected = any(
            d["state"] == "connected" and d["type"] in ("wifi", "ethernet")
            and d["connection"] != HOTSPOT and not d["connection"].startswith("gadget")
            for d in devices)
        return {"managed": True, "connected": connected, "hotspot_active": hotspot,
                "devices": devices, "error": self.last_error}

    def scan(self):
        out = self.nmcli("-t", "-f", "SSID,SIGNAL,SECURITY", "device", "wifi", "list", "--rescan", "yes")
        best = {}
        for line in out.splitlines():
            parts = split_terse(line)
            if len(parts) < 3 or not parts[0]:
                continue
            signal = int(parts[1]) if parts[1].isdigit() else 0
            if parts[0] not in best or signal > best[parts[0]]["signal"]:
                best[parts[0]] = {"ssid": parts[0], "signal": signal, "security": parts[2]}
        return sorted(best.values(), key=lambda n: -n["signal"])

    # -- applying the configuration -----------------------------------------------
    def apply(self):
        """Make NetworkManager match the YAML. Only changed items are recreated."""
        if not self.managed():
            return
        with self._lock:
            cfg = self.config.section("network")
            applied = self.storage.get(APPLIED_KEY) or {}
            existing = {c["name"]: c for c in self.connections()}
            new_applied = {}
            iface = self.interface()

            for wifi in cfg["wifi"]:
                name = WIFI_PREFIX + wifi["ssid"]
                digest = _hash(wifi)
                new_applied[name] = digest
                if name in existing and applied.get(name) == digest:
                    continue
                if name in existing:
                    self.nmcli("connection", "delete", name)
                args = ["connection", "add", "type", "wifi", "ifname", iface, "con-name", name,
                        "ssid", wifi["ssid"], "connection.autoconnect", "yes",
                        "connection.autoconnect-priority", str(wifi["priority"])]
                if wifi["password"]:
                    args += ["wifi-sec.key-mgmt", "wpa-psk", "wifi-sec.psk", wifi["password"]]
                self.nmcli(*args)
                log.info("Wi-Fi connection configured: %s", wifi["ssid"])

            for name in existing:
                if name.startswith(WIFI_PREFIX) and name not in new_applied:
                    self.nmcli("connection", "delete", name)
                    log.info("Wi-Fi connection removed: %s", name[len(WIFI_PREFIX):])

            hs = cfg["hotspot"]
            digest = _hash(hs)
            new_applied[HOTSPOT] = digest
            if not hs["enabled"]:
                if HOTSPOT in existing:
                    self.nmcli("connection", "delete", HOTSPOT)
                new_applied.pop(HOTSPOT)
            elif HOTSPOT not in existing or applied.get(HOTSPOT) != digest:
                if HOTSPOT in existing:
                    self.nmcli("connection", "delete", HOTSPOT)
                self.nmcli("connection", "add", "type", "wifi", "ifname", iface, "con-name", HOTSPOT,
                           "ssid", hs["ssid"], "connection.autoconnect", "no",
                           "802-11-wireless.mode", "ap", "802-11-wireless.band", "bg",
                           "ipv4.method", "shared",
                           "wifi-sec.key-mgmt", "wpa-psk", "wifi-sec.psk", hs["password"])
                log.info("Hotspot connection configured: %s", hs["ssid"])

            eth = cfg["ethernet"]
            digest = _hash(eth)
            wired = [c for c in existing.values()
                     if c["type"] in ("802-3-ethernet", "ethernet") and not c["name"].startswith("gadget")]
            if wired and applied.get("ethernet") != digest:
                name = wired[0]["name"]
                if eth["method"] == "manual":
                    self.nmcli("connection", "modify", name, "ipv4.method", "manual",
                               "ipv4.addresses", eth["address"], "ipv4.gateway", eth["gateway"],
                               "ipv4.dns", eth["dns"].replace(",", " "))
                else:
                    self.nmcli("connection", "modify", name, "ipv4.method", "auto",
                               "ipv4.addresses", "", "ipv4.gateway", "", "ipv4.dns", "")
                log.info("Ethernet configured (%s): %s", name, eth["method"])
                try:
                    self.nmcli("connection", "up", name)
                except NmcliError as exc:
                    log.info("Ethernet not brought up: %s", exc)
            new_applied["ethernet"] = digest
            self.storage.set(APPLIED_KEY, new_applied)
            self.last_error = None

        if self.status().get("hotspot_active") and cfg["wifi"]:
            # New networks while in hotspot mode: try them right away.
            self._leave_hotspot_and_retry()

    def apply_safe(self):
        try:
            self.apply()
        except Exception as exc:
            self.last_error = str(exc)
            log.error("Could not apply network configuration: %s", exc)

    # -- hotspot monitor ---------------------------------------------------------
    def _hotspot_up(self):
        log.warning("No network connection: starting hotspot %s", self.config.get("network.hotspot.ssid"))
        self.nmcli("connection", "up", HOTSPOT)
        self._hotspot_since = self._clock()

    def _leave_hotspot_and_retry(self, wait=30):
        log.info("Leaving hotspot to retry the known Wi-Fi networks")
        try:
            self.nmcli("connection", "down", HOTSPOT)
        except NmcliError:
            pass
        end = self._clock() + wait
        while self._clock() < end and not self._stop.is_set():
            if self.status()["connected"]:
                log.info("Connected again")
                self._hotspot_since = None
                self._no_conn_since = None
                return True
            self._stop.wait(3)
        self._hotspot_up()
        return False

    def check(self):
        """One monitor iteration (also used by the tests)."""
        if not self.managed():
            return
        st = self.status()
        hs = self.config.section("network")["hotspot"]
        now = self._clock()
        if st["connected"]:
            self._no_conn_since = None
            if st["hotspot_active"]:
                # Connected through Ethernet while the AP is up: the AP is no longer needed.
                self.nmcli("connection", "down", HOTSPOT)
                self._hotspot_since = None
            return
        if st["hotspot_active"]:
            if self._hotspot_since is None:
                self._hotspot_since = now
            quiet = now - self._last_web > WEB_QUIET
            if (self.config.get("network.wifi") and quiet
                    and now - self._hotspot_since >= hs["retry_interval"]):
                self._leave_hotspot_and_retry()
            return
        if not hs["enabled"]:
            return
        if self._no_conn_since is None:
            self._no_conn_since = now
        elif now - self._no_conn_since >= hs["timeout"]:
            self._hotspot_up()
            self._no_conn_since = None

    def start(self):
        def run():
            self.apply_safe()
            while not self._stop.wait(10):
                try:
                    self.check()
                except Exception as exc:
                    self.last_error = str(exc)
                    log.warning("Network monitor: %s", exc)
        self._thread = threading.Thread(target=run, name="network", daemon=True)
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()
