import time

import pytest

from stella.hw import system


@pytest.fixture
def board(monkeypatch):
    calls = []
    monkeypatch.setattr(system, "under_systemd", lambda: True)
    monkeypatch.setattr(system, "clock_synchronized", lambda: False)
    monkeypatch.setattr(system, "set_clock", lambda epoch: calls.append(epoch))
    return calls


def test_sets_clock_when_unsynced_and_far_off(board):
    target = time.time() + 1900
    result = system.sync_clock_from(target)
    assert result["changed"] is True and board == [target]
    assert abs(result["offset"] - 1900) < 5


def test_small_difference_is_ignored(board):
    assert system.sync_clock_from(time.time() + 5)["changed"] is False
    assert board == []


def test_ntp_synced_clock_is_never_touched(board, monkeypatch):
    monkeypatch.setattr(system, "clock_synchronized", lambda: True)
    assert system.sync_clock_from(time.time() + 3600)["changed"] is False
    assert board == []


def test_only_on_the_board(board, monkeypatch):
    monkeypatch.setattr(system, "under_systemd", lambda: False)
    assert system.sync_clock_from(time.time() + 3600)["changed"] is False
    assert board == []


def test_set_clock_pauses_ntp_and_restores_it(monkeypatch):
    cmds = []

    class R:
        returncode = 0
        stderr = ""
        stdout = ""
    monkeypatch.setattr(system, "_run", lambda cmd, timeout=10: cmds.append(cmd) or R())
    system.set_clock(1795310000)
    assert cmds[0][-2:] == ["set-ntp", "false"]
    assert cmds[1][:4] == ["sudo", "-n", "timedatectl", "set-time"]
    assert cmds[1][4].endswith(" UTC")
    assert cmds[-1][-2:] == ["set-ntp", "true"]


def test_clock_api_validates_input(tmp_path):
    from stella.app import App
    from stella.config import Config
    from stella.web import create_app

    config = Config(str(tmp_path / "config.yaml")).load()
    config.update_section("leds", {"driver": "none"}, notify=False)
    ctx = App(config, detector=object(), start_pipeline=False)
    client = create_app(ctx).test_client()
    h = {"Authorization": "Bearer " + config.get("api.token")}
    assert client.post("/api/v1/system/clock", json={"epoch": "x"}, headers=h).status_code == 400
    assert client.post("/api/v1/system/clock", json={"epoch": 1000}, headers=h).status_code == 400
    resp = client.post("/api/v1/system/clock", json={"epoch": time.time()}, headers=h)
    assert resp.status_code == 200 and resp.get_json()["changed"] is False  # PC: not under systemd
    ctx.stop()
