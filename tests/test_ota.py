import os
import shutil
import subprocess

import pytest

from stella.config import Config
from stella.ota import Ota, OtaError

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git no disponible")


def git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd)] + list(args), check=True, stdout=subprocess.PIPE,
                          universal_newlines=True).stdout.strip()


def commit(repo, name, content):
    (repo / name).write_text(content)
    git(repo, "add", name)
    git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "change " + name)
    return git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repos(tmp_path):
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    git(upstream, "init", "-q", "-b", "main")
    first = commit(upstream, "a.txt", "1")
    device = tmp_path / "device"
    subprocess.run(["git", "clone", "-q", str(upstream), str(device)], check=True)
    data = tmp_path / "data"
    data.mkdir()
    config = Config(str(data / "config.yaml")).load()
    config.update_section("ota", {"repo_url": str(upstream), "branch": "main"})
    return upstream, device, config, first


def test_check_apply_and_confirm(repos):
    upstream, device, config, first = repos
    restarts = []
    ota = Ota(config, repo_dir=str(device), restart=lambda: restarts.append(1))
    assert ota.check()["available"] is False

    second = commit(upstream, "b.txt", "2")
    state = ota.check()
    assert state["available"] is True and len(state["commits"]) == 1

    state = ota.apply()
    assert git(device, "rev-parse", "HEAD") == second
    assert state["pending"] is True
    with open(ota.prev_file) as fh:
        assert fh.read().strip() == first
    ota.mark_healthy()
    assert ota.pending() is False
    with pytest.raises(OtaError):
        ota.apply()  # nothing new checked


def test_requires_repo_url(repos):
    _, device, config, _ = repos
    config.update_section("ota", {"repo_url": ""})
    with pytest.raises(OtaError):
        Ota(config, repo_dir=str(device)).check()


def test_rollback_script(repos, tmp_path):
    upstream, device, config, first = repos
    second = commit(upstream, "b.txt", "2")
    ota = Ota(config, repo_dir=str(device), restart=lambda: None)
    ota.check()
    ota.apply()
    assert git(device, "rev-parse", "HEAD") == second

    # Fake venv python (pip) and sudo so the script runs on the PC.
    venv = tmp_path / "venv" / "bin"
    venv.mkdir(parents=True)
    (venv / "python").write_text("#!/bin/sh\nexit 0\n")
    (venv / "python").chmod(0o755)
    fakebin = tmp_path / "fakebin"
    fakebin.mkdir()
    log = tmp_path / "sudo.log"
    (fakebin / "sudo").write_text("#!/bin/sh\necho \"$@\" >> %s\n" % log)
    (fakebin / "sudo").chmod(0o755)

    env = dict(os.environ, STELLA_REPO=str(device), STELLA_DATA=config.data_dir,
               STELLA_VENV=str(tmp_path / "venv"), PATH=str(fakebin) + os.pathsep + os.environ["PATH"])
    subprocess.run(["sh", os.path.join(ROOT, "deploy", "rollback.sh")], env=env, check=True,
                   stdout=subprocess.PIPE)
    assert git(device, "rev-parse", "HEAD") == first
    assert not os.path.exists(ota.prev_file)
    assert "systemctl start stella.service" in log.read_text()
    # After the rollback Stella starts again (new process): the UI explains what happened.
    assert "falló" in Ota(config, repo_dir=str(device)).state()["message"]

    # Without a pending update the script does nothing.
    subprocess.run(["sh", os.path.join(ROOT, "deploy", "rollback.sh")], env=env, check=True,
                   stdout=subprocess.PIPE)
    assert git(device, "rev-parse", "HEAD") == first
