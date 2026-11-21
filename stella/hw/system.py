"""System information and actions (temperature, IPs, timezone, restart)."""
import logging
import os
import subprocess
import sys
import time

log = logging.getLogger(__name__)

THERMAL_ZONE = "/sys/class/thermal/thermal_zone0/temp"
ZONEINFO = "/usr/share/zoneinfo"
_START = time.time()
# Container/VM bridges of a development PC; never present on the board.
VIRTUAL_IFACES = ("docker", "br-", "virbr", "veth", "lo")


def temperature():
    """CPU temperature in °C, or None if unavailable."""
    try:
        with open(THERMAL_ZONE) as fh:
            return round(int(fh.read().strip()) / 1000.0, 1)
    except (OSError, ValueError):
        return None


def ip_addresses():
    """{interface: ipv4} for every interface except loopback."""
    try:
        out = subprocess.run(["ip", "-o", "-4", "addr", "show"], stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, universal_newlines=True, timeout=3).stdout
    except (OSError, subprocess.TimeoutExpired):
        return {}
    result = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) < 4 or parts[2] != "inet" or parts[1].startswith(VIRTUAL_IFACES):
            continue
        if parts[1] != "lo":
            result.setdefault(parts[1], parts[3].split("/")[0])
    return result


def system_uptime():
    try:
        with open("/proc/uptime") as fh:
            return int(float(fh.read().split()[0]))
    except (OSError, ValueError, IndexError):
        return None


def process_uptime():
    return int(time.time() - _START)


def valid_timezone(name):
    return bool(name) and ".." not in name and os.path.isfile(os.path.join(ZONEINFO, name))


def apply_timezone(name):
    """Set the process timezone (the board clock stays in UTC)."""
    if not valid_timezone(name):
        log.warning("Unknown timezone %r, keeping the system one", name)
        return False
    os.environ["TZ"] = name
    time.tzset()
    log.info("Timezone set to %s", name)
    return True


def timezones():
    names = []
    for region in ("Africa", "America", "Antarctica", "Asia", "Atlantic", "Australia", "Europe",
                   "Indian", "Pacific"):
        base = os.path.join(ZONEINFO, region)
        for root, _, files in os.walk(base):
            for name in files:
                names.append(os.path.relpath(os.path.join(root, name), ZONEINFO))
    names.append("UTC")
    return sorted(names)


def under_systemd():
    return "INVOCATION_ID" in os.environ


def restart_service(service="stella", delay=1.0):
    """Restart Stella: via systemd on the board, by re-executing itself otherwise."""
    if under_systemd():
        cmd = "sleep %s; sudo -n systemctl restart %s" % (float(delay), service)
        subprocess.Popen(["sh", "-c", cmd], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return "systemd"
    log.warning("Not under systemd: re-executing the process")
    time.sleep(delay)
    os.execv(sys.executable, [sys.executable, "-m", "stella"] + sys.argv[1:])
    return "exec"


def reboot(delay=1.0):
    if not under_systemd():
        raise RuntimeError("Reiniciar el equipo solo está permitido en la placa")
    subprocess.Popen(["sh", "-c", "sleep %s; sudo -n reboot" % float(delay)], start_new_session=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
