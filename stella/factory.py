"""Factory reset: forget Wi-Fi networks, data and configuration.

What is reset:
- every Wi-Fi connection in NetworkManager (clients and hotspot), when the
  network is managed by Stella; USB gadget and Ethernet are never touched;
- ``events.db`` (history, counters, pending deliveries) and OTA markers;
- ``config.yaml``, replaced by ``<data>/factory.yaml`` if it exists or by the
  repository's ``config.example.yaml`` (admin/stella, new API token).
"""
import logging
import os
import shutil

log = logging.getLogger(__name__)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_FILES = ("events.db", "events.db-wal", "events.db-shm", "ota_prev", "ota_rolled_back")
CONFIRM_WORD = "RESTAURAR"


def factory_source(data_dir):
    custom = os.path.join(data_dir, "factory.yaml")
    return custom if os.path.isfile(custom) else os.path.join(ROOT, "config.example.yaml")


def factory_reset(config, network=None, release=None):
    """Reset the device. ``release()`` must close whatever uses the data files.

    Returns a summary dict. Does not restart anything.
    """
    summary = {"wifi_removed": [], "files_removed": [], "config_from": factory_source(config.data_dir)}
    log.warning("FACTORY RESET requested")

    if network is not None and config.get("network.managed"):
        try:
            summary["wifi_removed"] = network.delete_all_wifi()
        except Exception as exc:
            log.error("Factory reset: could not remove Wi-Fi connections: %s", exc)
            summary["wifi_error"] = str(exc)

    if release is not None:
        release()

    for name in DATA_FILES:
        path = os.path.join(config.data_dir, name)
        if os.path.exists(path):
            os.unlink(path)
            summary["files_removed"].append(name)

    tmp = config.path + ".factory"
    shutil.copyfile(summary["config_from"], tmp)
    os.chmod(tmp, 0o600)
    os.replace(tmp, config.path)
    log.warning("Factory reset done: config from %s, Wi-Fi removed: %s",
                summary["config_from"], ", ".join(summary["wifi_removed"]) or "(none)")
    return summary
