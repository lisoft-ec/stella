"""Over-the-air updates from a git repository, with automatic rollback.

Flow:
1. ``check()``: ``git fetch`` the configured branch and list the new commits.
2. ``apply()``: store the current commit in ``<data>/ota_prev``, move the
   working tree to the fetched commit, reinstall requirements if they
   changed and restart the service.
3. After ``ota.healthy_after`` seconds running, ``mark_healthy()`` deletes
   ``ota_prev``. If Stella keeps crashing before that, systemd runs
   ``stella-rollback.service`` (deploy/rollback.sh), which goes back to the
   commit in ``ota_prev``.
"""
import hashlib
import logging
import os
import subprocess
import sys
import threading

from .hw import system

log = logging.getLogger(__name__)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REQUIREMENTS = "requirements-board.txt"


class OtaError(RuntimeError):
    pass


def _file_hash(path):
    try:
        with open(path, "rb") as fh:
            return hashlib.sha256(fh.read()).hexdigest()
    except OSError:
        return None


class Ota:
    def __init__(self, config, repo_dir=ROOT, restart=None):
        self.config = config
        self.repo = repo_dir
        self._restart = restart or (lambda: system.restart_service(self.config.get("ota.service", "stella")))
        self._lock = threading.Lock()
        self._last = {"available": False, "commits": [], "message": "", "target": None}
        self.prev_file = os.path.join(config.data_dir, "ota_prev")
        self.rolled_back_file = os.path.join(config.data_dir, "ota_rolled_back")

    def git(self, *args, timeout=120):
        try:
            proc = subprocess.run(["git", "-C", self.repo] + list(args), stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, universal_newlines=True, timeout=timeout)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise OtaError("git: %s" % exc)
        if proc.returncode != 0:
            raise OtaError("git %s: %s" % (args[0], (proc.stderr or proc.stdout).strip()))
        return proc.stdout.strip()

    def current(self):
        try:
            return self.git("rev-parse", "HEAD")
        except OtaError:
            return None

    def pending(self):
        return os.path.exists(self.prev_file)

    def state(self):
        with self._lock:
            state = dict(self._last)
        state.update({
            "current": self.current(),
            "pending": self.pending(),
            "repo_url": self.config.get("ota.repo_url"),
            "branch": self.config.get("ota.branch"),
        })
        if os.path.exists(self.rolled_back_file) and not state["message"]:
            with open(self.rolled_back_file) as fh:
                state["message"] = ("La última actualización falló y se volvió a la versión %s"
                                    % fh.read().strip()[:8])
        return state

    def _remote(self):
        url = (self.config.get("ota.repo_url") or "").strip()
        if not url:
            raise OtaError("Configura primero la URL del repositorio")
        try:
            current = self.git("remote", "get-url", "origin")
        except OtaError:
            self.git("remote", "add", "origin", url)
        else:
            if current != url:
                self.git("remote", "set-url", "origin", url)
        return url

    def check(self):
        with self._lock:
            self._remote()
            branch = self.config.get("ota.branch") or "master"
            self.git("fetch", "--quiet", "origin", branch)
            target = self.git("rev-parse", "FETCH_HEAD")
            commits = self.git("log", "--oneline", "-20", "HEAD..%s" % target)
            commits = [c for c in commits.splitlines() if c]
            behind = self.git("rev-list", "--count", "%s..HEAD" % target)
            if commits:
                message = "Hay %d cambio(s) nuevo(s) en %s" % (len(commits), branch)
            elif int(behind or 0):
                message = "La versión instalada tiene cambios que no están en %s" % branch
            else:
                message = "Stella está actualizada"
            self._last = {"available": bool(commits), "commits": commits, "message": message,
                          "target": target}
        return self.state()

    def apply(self):
        with self._lock:
            target = self._last.get("target")
            if not self._last.get("available") or not target:
                raise OtaError("No hay ninguna actualización comprobada para instalar")
            prev = self.current()
            req_path = os.path.join(self.repo, REQUIREMENTS)
            req_before = _file_hash(req_path)
            with open(self.prev_file, "w") as fh:
                fh.write(prev + "\n")
            if os.path.exists(self.rolled_back_file):
                os.unlink(self.rolled_back_file)
            log.warning("OTA: updating %s -> %s", prev[:8], target[:8])
            self.git("reset", "--hard", target)
            if _file_hash(req_path) != req_before:
                log.info("OTA: requirements changed, installing")
                proc = subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", req_path],
                                      stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                      universal_newlines=True, timeout=1800)
                if proc.returncode != 0:
                    log.error("OTA: pip failed, rolling back:\n%s", proc.stdout[-2000:])
                    self.git("reset", "--hard", prev)
                    os.unlink(self.prev_file)
                    raise OtaError("Fallo al instalar dependencias; se mantiene la versión anterior")
            self._last = {"available": False, "commits": [], "message": "Actualización instalada, reiniciando…",
                          "target": None}
        threading.Thread(target=self._restart, name="ota-restart", daemon=True).start()
        return self.state()

    def mark_healthy(self):
        """The new version has been running fine: confirm the update."""
        if self.pending():
            os.unlink(self.prev_file)
            log.info("OTA: update confirmed (%s)", (self.current() or "")[:8])
