import os
import stat

import pytest
import yaml

from stella.app import App
from stella.config import Config
from stella.factory import factory_reset, factory_source
from stella.web import create_app
from tests.test_leds_network import FakeNmcli

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def ctx(tmp_path):
    config = Config(str(tmp_path / "config.yaml")).load()
    config.update_section("leds", {"driver": "none"}, notify=False)
    app = App(config, detector=object(), start_pipeline=False)
    app.network._runner = FakeNmcli()
    yield app
    app.stop()


def test_factory_source_prefers_custom_file(tmp_path):
    assert factory_source(str(tmp_path)).endswith("config.example.yaml")
    (tmp_path / "factory.yaml").write_text("device: {id: x}\n")
    assert factory_source(str(tmp_path)) == str(tmp_path / "factory.yaml")


def test_factory_reset_wipes_wifi_data_and_config(ctx):
    config = ctx.config
    config.update_section("network", {"managed": True}, notify=False)
    config.update_section("device", {"id": "puerta-9"}, notify=False)
    nm = ctx.network._runner
    nm.connections["WIFI-IOT"] = "802-11-wireless"
    from stella.vision.tracker import Track
    ctx.on_crossing("in", Track(1, (0, 0, 5, 5)))
    old_token = config.get("api.token")
    db = os.path.join(config.data_dir, "events.db")
    assert os.path.exists(db)

    summary = ctx.factory_reset(restart=False)

    assert summary["wifi_removed"] == ["WIFI-IOT"]
    assert "gadget0" in nm.connections and "Wired connection 1" in nm.connections
    assert not os.path.exists(db)
    assert stat.S_IMODE(os.stat(config.path).st_mode) == 0o600
    with open(config.path) as fh, open(os.path.join(ROOT, "config.example.yaml")) as ex:
        assert yaml.safe_load(fh) == yaml.safe_load(ex)
    fresh = Config(config.path).load()
    assert fresh.get("device.id") == "stella-01"
    assert fresh.get("api.token") != old_token
    assert fresh.get("web.default_password") is True


def test_factory_reset_unmanaged_network_is_not_touched(ctx):
    nm = ctx.network._runner
    nm.connections["WIFI-IOT"] = "802-11-wireless"
    summary = ctx.factory_reset(restart=False)
    assert summary["wifi_removed"] == []
    assert "WIFI-IOT" in nm.connections


def login(client):
    import re
    client.post("/login", data={"username": "admin", "password": "stella"})
    page = client.get("/sistema").get_data(as_text=True)
    return re.search(r'name="csrf-token" content="([^"]+)"', page).group(1)


def test_factory_reset_api_requires_session_and_confirmation(ctx, monkeypatch):
    calls = []
    monkeypatch.setattr(ctx, "factory_reset", lambda: calls.append(1))
    app = create_app(ctx)
    client = app.test_client()
    token = {"Authorization": "Bearer " + ctx.config.get("api.token")}
    assert client.post("/api/v1/system/factory-reset", json={"confirm": "RESTAURAR"},
                       headers=token).status_code == 403
    csrf = login(client)
    h = {"X-CSRF-Token": csrf}
    assert client.post("/api/v1/system/factory-reset", json={"confirm": "si"}, headers=h).status_code == 400
    resp = client.post("/api/v1/system/factory-reset", json={"confirm": "RESTAURAR"}, headers=h)
    assert resp.status_code == 200 and resp.get_json()["ok"]
    import time
    time.sleep(1.3)
    assert calls == [1]


def test_led_test_api(ctx):
    app = create_app(ctx)
    client = app.test_client()
    token = {"Authorization": "Bearer " + ctx.config.get("api.token")}
    resp = client.post("/api/v1/leds/test", json={"color": [1, 0, 1], "seconds": 2}, headers=token)
    assert resp.status_code == 200 and resp.get_json()["driver"] == "none"
    assert ctx.leds.desired() == (1, 0, 1)
    assert client.post("/api/v1/leds/test", json={"color": [1]}, headers=token).status_code == 400
    assert client.post("/api/v1/leds/test", json={"sequence": True}, headers=token).status_code == 200
