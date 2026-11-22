"""YAML configuration: defaults, loading, validation and atomic saving.

The configuration is a plain nested dict. ``DEFAULTS`` documents every key;
the file on disk only needs the keys that differ from the defaults.
"""
import copy
import logging
import os
import secrets
import tempfile
import threading

import yaml

log = logging.getLogger(__name__)

SECRET_MASK = "********"
# pbkdf2 is understood by Werkzeug 2.2 (board) and 3.x (PC); 3.x defaults to scrypt.
PASSWORD_METHOD = "pbkdf2:sha256"

# Keys (dotted paths) never returned to clients in clear text.
SECRET_KEYS = (
    "web.password_hash",
    "web.secret_key",
    "api.token",
    "mqtt.password",
)

DEFAULTS = {
    "device": {
        "id": "stella-01",
        "name": "Stella",
        "timezone": "America/Guayaquil",
    },
    "web": {
        "host": "0.0.0.0",
        "port": 7777,
        "username": "admin",
        "password_hash": "",
        "default_password": True,
        "secret_key": "",
        "preview_fps": 5,
        "preview_width": 640,
        "jpeg_quality": 70,
    },
    "api": {
        "token": "",
    },
    "camera": {
        # "/dev/video0", a camera index (0) or a video file path.
        "source": "/dev/video0",
        "width": 640,
        "height": 480,
        "fps": 30,
        "flip_x": False,
        "flip_y": False,
        # Video files only: start again when the file ends.
        "loop": False,
        # Video files only: play at the file's frame rate instead of as fast as possible.
        "realtime": True,
        # Coral camera (OV5645): disable autofocus via sysfs.
        "disable_autofocus": True,
    },
    "detector": {
        "model": "models/ssd_mobilenet_v2_coco_quant_postprocess_edgetpu.tflite",
        # "edgetpu" on the Coral board, "none" for CPU.
        "delegate": "edgetpu",
        "threshold": 0.5,
        "max_objects": 10,
        "person_label": 0,
        "threads": 2,
    },
    "motion": {
        # MOG2 gate: inference only runs while there is motion inside the ROI.
        "enabled": True,
        "threshold_percent": 1.0,
        # Frames without any detection before inference is switched off again.
        "idle_frames": 10,
        "history": 500,
        "var_threshold": 16,
    },
    "tracking": {
        "iou_threshold": 0.2,
        # Frames a track may go undetected before it is closed.
        "max_missing": 5,
    },
    "counting": {
        # Normalized (0..1) coordinates relative to the camera frame.
        "roi": [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]],
        "line": [[0.0, 0.5], [1.0, 0.5]],
        # False: crossing from the left side of the line (p1->p2) to its right is "in".
        "invert": False,
        # 0 = no limit.
        "occupancy_limit": 0,
        # Daily counters reset at this local time (HH:MM).
        "reset_time": "00:00",
    },
    "mqtt": {
        "enabled": False,
        "host": "localhost",
        "port": 1883,
        "username": "",
        "password": "",
        "topic_prefix": "stella",
        "keepalive": 60,
        "status_interval": 60,
        "homeassistant": True,
        "discovery_prefix": "homeassistant",
    },
    "webhook": {
        "enabled": False,
        "url": "",
        "headers": {},
        "timeout": 5,
    },
    "network": {
        # When False Stella never touches NetworkManager (PC / development).
        "managed": False,
        # The board user is in the "netdev" group: polkit lets it use nmcli without sudo.
        "use_sudo": False,
        "interface": "wlan0",
        "wifi": [],  # [{ssid, password, priority, hidden}]
        "hotspot": {
            "enabled": True,
            "ssid": "StellaWIFI",
            "password": "stella1234",
            # Seconds without a connection before the hotspot is started.
            "timeout": 90,
            # Seconds between attempts to go back to a known network.
            "retry_interval": 300,
        },
        "ethernet": {
            # "auto" (DHCP) or "manual".
            "method": "auto",
            "address": "",
            "gateway": "",
            "dns": "",
        },
    },
    "leds": {
        # "gpio" on the Coral board, "none" elsewhere.
        "driver": "gpio",
        # Header pins: red = GPIO_P18, green = GPIO_P13, blue = GPIO_P16 (sysfs numbers).
        "pins": {"red": 138, "green": 6, "blue": 73},
        # 0 = common-anode LED (a colour lights when its pin is low), 1 = common cathode.
        "active_level": 0,
        "flash_seconds": 1.0,
        "colors": {
            "entry": [0, 1, 0],
            "exit": [1, 1, 0],
            "no_network": [0, 0, 1],
            "hotspot": [1, 0, 1],
            "error": [1, 0, 0],
            "full": [1, 0, 0],
        },
    },
    "ota": {
        "repo_url": "",
        "branch": "main",
        "service": "stella",
        "healthy_after": 60,
    },
}


class ConfigError(ValueError):
    pass


def deep_merge(base, override):
    """Return a new dict: ``base`` updated recursively with ``override``."""
    result = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def get_path(data, dotted):
    node = data
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def set_path(data, dotted, value):
    parts = dotted.split(".")
    node = data
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = value


def _point(value, name):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ConfigError("%s: se espera un punto [x, y]" % name)
    x, y = float(value[0]), float(value[1])
    if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
        raise ConfigError("%s: coordenadas normalizadas entre 0 y 1" % name)
    return [x, y]


def _hhmm(value):
    try:
        hh, mm = str(value).split(":")
        hh, mm = int(hh), int(mm)
    except ValueError:
        raise ConfigError("counting.reset_time: formato HH:MM")
    if not (0 <= hh < 24 and 0 <= mm < 60):
        raise ConfigError("counting.reset_time: hora no válida")
    return "%02d:%02d" % (hh, mm)


def validate(cfg):
    """Normalize types in place and raise ConfigError on invalid values."""
    cam = cfg["camera"]
    cam["width"], cam["height"], cam["fps"] = int(cam["width"]), int(cam["height"]), int(cam["fps"])
    if cam["width"] <= 0 or cam["height"] <= 0 or cam["fps"] <= 0:
        raise ConfigError("camera: ancho, alto y fps deben ser positivos")
    src = cam["source"]
    if isinstance(src, str) and src.isdigit():
        cam["source"] = int(src)

    det = cfg["detector"]
    det["threshold"] = float(det["threshold"])
    if not 0.0 < det["threshold"] < 1.0:
        raise ConfigError("detector.threshold: entre 0 y 1")
    det["max_objects"] = int(det["max_objects"])
    if det["delegate"] not in ("edgetpu", "none"):
        raise ConfigError("detector.delegate: 'edgetpu' o 'none'")

    mot = cfg["motion"]
    mot["threshold_percent"] = float(mot["threshold_percent"])
    mot["idle_frames"] = int(mot["idle_frames"])

    trk = cfg["tracking"]
    trk["iou_threshold"] = float(trk["iou_threshold"])
    trk["max_missing"] = int(trk["max_missing"])

    cnt = cfg["counting"]
    roi = cnt["roi"]
    if not isinstance(roi, list) or len(roi) < 3:
        raise ConfigError("counting.roi: al menos 3 puntos")
    cnt["roi"] = [_point(p, "counting.roi") for p in roi]
    line = cnt["line"]
    if not isinstance(line, list) or len(line) != 2:
        raise ConfigError("counting.line: exactamente 2 puntos")
    cnt["line"] = [_point(p, "counting.line") for p in line]
    if cnt["line"][0] == cnt["line"][1]:
        raise ConfigError("counting.line: los dos puntos no pueden coincidir")
    cnt["invert"] = bool(cnt["invert"])
    cnt["occupancy_limit"] = max(0, int(cnt["occupancy_limit"]))
    cnt["reset_time"] = _hhmm(cnt["reset_time"])

    mq = cfg["mqtt"]
    mq["port"] = int(mq["port"])
    mq["status_interval"] = max(5, int(mq["status_interval"]))
    mq["topic_prefix"] = str(mq["topic_prefix"]).strip("/")
    if not mq["topic_prefix"]:
        raise ConfigError("mqtt.topic_prefix no puede estar vacío")

    wh = cfg["webhook"]
    if wh["enabled"] and not str(wh["url"]).startswith(("http://", "https://")):
        raise ConfigError("webhook.url debe empezar por http:// o https://")
    if not isinstance(wh["headers"], dict):
        raise ConfigError("webhook.headers debe ser un diccionario")

    net = cfg["network"]
    wifi = []
    for item in net["wifi"] or []:
        ssid = str(item.get("ssid", "")).strip()
        if not ssid:
            raise ConfigError("network.wifi: cada red necesita un ssid")
        password = str(item.get("password", "") or "")
        if password and len(password) < 8:
            raise ConfigError("network.wifi: la clave de '%s' debe tener al menos 8 caracteres" % ssid)
        wifi.append({"ssid": ssid, "password": password, "priority": int(item.get("priority", 0) or 0),
                     "hidden": bool(item.get("hidden", False))})
    net["wifi"] = wifi
    hs = net["hotspot"]
    if hs["enabled"] and len(str(hs["password"])) < 8:
        raise ConfigError("network.hotspot.password: al menos 8 caracteres")
    if net["ethernet"]["method"] not in ("auto", "manual"):
        raise ConfigError("network.ethernet.method: 'auto' o 'manual'")

    leds = cfg["leds"]
    if leds["driver"] not in ("gpio", "none"):
        raise ConfigError("leds.driver: 'gpio' o 'none'")
    if int(leds["active_level"]) not in (0, 1):
        raise ConfigError("leds.active_level: 0 (ánodo común) o 1 (cátodo común)")
    leds["active_level"] = int(leds["active_level"])
    return cfg


def generate_secrets(cfg):
    """Fill empty secrets. Returns True if something changed."""
    from werkzeug.security import generate_password_hash

    changed = False
    if not cfg["web"]["secret_key"]:
        cfg["web"]["secret_key"] = secrets.token_hex(32)
        changed = True
    if not cfg["api"]["token"]:
        cfg["api"]["token"] = secrets.token_urlsafe(32)
        changed = True
    if not cfg["web"]["password_hash"]:
        cfg["web"]["password_hash"] = generate_password_hash("stella", method=PASSWORD_METHOD)
        cfg["web"]["default_password"] = True
        changed = True
    return changed


def redact(cfg):
    """Copy of the config with secrets replaced by a mask (or '' if unset)."""
    out = copy.deepcopy(cfg)
    for key in SECRET_KEYS:
        value = get_path(out, key)
        if value is not None:
            set_path(out, key, SECRET_MASK if value else "")
    for item in get_path(out, "network.wifi") or []:
        item["password"] = SECRET_MASK if item.get("password") else ""
    return out


def unmask(new_section, old_section):
    """Replace masked secrets coming back from a client with the stored values."""
    if isinstance(new_section, dict) and isinstance(old_section, dict):
        return {
            k: (old_section.get(k) if v == SECRET_MASK else unmask(v, old_section.get(k)))
            for k, v in new_section.items()
        }
    if isinstance(new_section, list) and isinstance(old_section, list):
        # Wi-Fi list: match by SSID.
        by_ssid = {i.get("ssid"): i for i in old_section if isinstance(i, dict)}
        result = []
        for item in new_section:
            if isinstance(item, dict) and item.get("password") == SECRET_MASK:
                item = dict(item, password=by_ssid.get(item.get("ssid"), {}).get("password", ""))
            result.append(item)
        return result
    return new_section


class Config:
    """Thread-safe holder of the configuration with load/save to YAML."""

    def __init__(self, path):
        self.path = os.path.abspath(path)
        self.data_dir = os.path.dirname(self.path)
        self._lock = threading.RLock()
        self._data = None
        self._listeners = []

    # -- loading / saving -------------------------------------------------
    def load(self):
        raw = {}
        if os.path.exists(self.path):
            with open(self.path) as fh:
                raw = yaml.safe_load(fh) or {}
        data = validate(deep_merge(DEFAULTS, raw))
        changed = generate_secrets(data)
        with self._lock:
            self._data = data
        if changed or not os.path.exists(self.path):
            self.save()
        return self

    def save(self):
        with self._lock:
            text = yaml.safe_dump(self._data, sort_keys=False, allow_unicode=True)
        os.makedirs(self.data_dir, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.data_dir, prefix=".config-", suffix=".yaml")
        try:
            with os.fdopen(fd, "w") as fh:
                fh.write(text)
            os.chmod(tmp, 0o600)
            os.replace(tmp, self.path)
        except Exception:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    # -- access ------------------------------------------------------------
    def snapshot(self):
        with self._lock:
            return copy.deepcopy(self._data)

    def get(self, dotted, default=None):
        with self._lock:
            value = get_path(self._data, dotted)
        return copy.deepcopy(value) if value is not None else default

    def section(self, name):
        return self.get(name, {})

    def resolve_path(self, path):
        """Relative paths in the config are relative to the repository root."""
        if os.path.isabs(path):
            return path
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(root, path)

    def on_change(self, callback):
        """Register ``callback(section_name)`` called after a section changes."""
        self._listeners.append(callback)

    def update_section(self, name, values, notify=True):
        """Merge ``values`` into section ``name``, validate, persist, notify."""
        with self._lock:
            if name not in self._data:
                raise ConfigError("Sección desconocida: %s" % name)
            current = self._data[name]
            values = unmask(values, current)
            if isinstance(current, dict):
                merged = deep_merge(current, values)
                # Lists and dicts like wifi/headers are replaced, not merged.
                for key, value in values.items():
                    if isinstance(value, list):
                        merged[key] = value
                    if key == "headers" and isinstance(value, dict):
                        merged[key] = value
            else:
                merged = values
            candidate = copy.deepcopy(self._data)
            candidate[name] = merged
            validate(candidate)
            self._data = candidate
            self.save()
        if notify:
            for callback in list(self._listeners):
                try:
                    callback(name)
                except Exception:
                    log.exception("Config listener failed for section %s", name)
        return self.get(name)
