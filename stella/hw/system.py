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


# -- clock ------------------------------------------------------------------
# Without Internet (hotspot mode) the board cannot sync NTP and its clock may
# be wrong after a reboot. The web UI sends the browser's time; it is applied
# only on the board, only when NTP is not synchronized and only if it differs.
CLOCK_TOLERANCE = 30  # seconds


def _run(cmd, timeout=10):
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          universal_newlines=True, timeout=timeout)


def clock_synchronized():
    """True/False from systemd-timedated, None if it cannot be asked."""
    try:
        out = _run(["timedatectl", "show", "-p", "NTPSynchronized", "--value"]).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return None
    return {"yes": True, "no": False}.get(out)


def set_clock(epoch):
    """Set the system clock and the RTC (UTC). NTP is paused while setting it."""
    stamp = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(epoch))
    _run(["sudo", "-n", "timedatectl", "set-ntp", "false"])
    try:
        result = _run(["sudo", "-n", "timedatectl", "set-time", stamp])
        if result.returncode != 0:
            # Fallback without RTC: at least fix the running clock.
            result = _run(["sudo", "-n", "date", "-u", "-s", "@%d" % int(epoch)])
            if result.returncode != 0:
                raise RuntimeError(result.stderr.strip() or "no se pudo ajustar la hora")
    finally:
        _run(["sudo", "-n", "timedatectl", "set-ntp", "true"])


def sync_clock_from(epoch):
    """Apply a client's time if appropriate. Returns ``{changed, offset, reason}``."""
    offset = float(epoch) - time.time()
    if not under_systemd():
        return {"changed": False, "offset": round(offset, 1), "reason": "solo en la placa"}
    if clock_synchronized():
        return {"changed": False, "offset": round(offset, 1), "reason": "la hora ya está sincronizada (NTP)"}
    if abs(offset) < CLOCK_TOLERANCE:
        return {"changed": False, "offset": round(offset, 1), "reason": "la diferencia es pequeña"}
    before = time.strftime("%Y-%m-%d %H:%M:%S")
    set_clock(epoch)
    log.warning("Clock set from the web browser: %s -> %s (offset %+.0f s)",
                before, time.strftime("%Y-%m-%d %H:%M:%S"), offset)
    return {"changed": True, "offset": round(offset, 1), "reason": "hora ajustada"}
