import re

import pytest

from stella.app import App
from stella.config import SECRET_MASK, Config
from stella.vision.tracker import Track
from stella.web import create_app


@pytest.fixture
def ctx(tmp_path):
    config = Config(str(tmp_path / "config.yaml")).load()
    config.update_section("leds", {"driver": "none"})
    app = App(config, detector=object(), start_pipeline=False)
    yield app
    app.storage.close()


@pytest.fixture
def client(ctx):
    flask_app = create_app(ctx)
    flask_app.testing = True
    return flask_app.test_client()


def login(client, password="stella"):
    resp = client.post("/login", data={"username": "admin", "password": password})
    page = client.get("/").get_data(as_text=True)
    match = re.search(r'name="csrf-token" content="([^"]+)"', page)
    return resp, (match.group(1) if match else None)


def bearer(ctx):
    return {"Authorization": "Bearer " + ctx.config.get("api.token")}


def test_requires_auth(client):
    assert client.get("/").status_code == 302
    assert client.get("/api/v1/status").status_code == 401
    assert client.get("/video.mjpg").status_code == 401


def test_login_wrong_password(client):
    resp = client.post("/login", data={"username": "admin", "password": "nope"})
    assert resp.status_code == 200
    assert "incorrectos" in resp.get_data(as_text=True)


def test_session_pages_and_csrf(client):
    resp, csrf = login(client)
    assert resp.status_code == 302 and csrf
    for path in ("/", "/calibracion", "/red", "/integraciones", "/sistema"):
        assert client.get(path).status_code == 200, path
    # Mutating request without CSRF header is rejected.
    assert client.post("/api/v1/counters/reset", json={}).status_code == 403
    resp = client.post("/api/v1/counters/reset", json={"occupancy": 3}, headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 200 and resp.get_json()["occupancy"] == 3


def test_token_auth_and_counters(ctx, client):
    ctx.on_crossing("in", Track(1, (0, 0, 10, 10)))
    ctx.on_crossing("out", Track(2, (0, 0, 10, 10)))
    data = client.get("/api/v1/counters", headers=bearer(ctx)).get_json()
    assert (data["in"], data["out"], data["occupancy"]) == (1, 1, 0)
    events = client.get("/api/v1/events?limit=10", headers=bearer(ctx)).get_json()
    assert [e["direction"] for e in events] == ["out", "in"]
    assert events[0]["counters"]["out"] == 1
    assert client.get("/api/v1/status", headers=bearer(ctx)).get_json()["counters"]["in"] == 1
    bad = {"Authorization": "Bearer wrong"}
    assert client.get("/api/v1/counters", headers=bad).status_code == 401


def test_config_is_redacted_and_updatable(ctx, client):
    ctx.config.update_section("mqtt", {"password": "s3cret"})
    cfg = client.get("/api/v1/config", headers=bearer(ctx)).get_json()
    assert cfg["mqtt"]["password"] == SECRET_MASK
    assert cfg["web"]["password_hash"] == SECRET_MASK
    resp = client.put("/api/v1/config/counting", headers=bearer(ctx),
                      json={"line": [[0.1, 0.4], [0.9, 0.6]], "invert": True})
    assert resp.status_code == 200
    assert ctx.config.get("counting.invert") is True
    resp = client.put("/api/v1/config/counting", headers=bearer(ctx), json={"roi": [[0, 0]]})
    assert resp.status_code == 400 and "roi" in resp.get_json()["error"]
    # Protected keys of "web" cannot be changed through PUT.
    client.put("/api/v1/config/web", headers=bearer(ctx), json={"password_hash": "x", "preview_fps": 3})
    assert ctx.config.get("web.password_hash") != "x"
    assert ctx.config.get("web.preview_fps") == 3
    assert client.put("/api/v1/config/api", headers=bearer(ctx), json={"token": "x"}).status_code == 404


def test_password_change_and_token_are_session_only(ctx, client):
    assert client.post("/api/v1/auth/token", headers=bearer(ctx)).status_code == 403
    _, csrf = login(client)
    h = {"X-CSRF-Token": csrf}
    resp = client.post("/api/v1/auth/password", json={"current": "bad", "new": "12345678"}, headers=h)
    assert resp.status_code == 400
    resp = client.post("/api/v1/auth/password", json={"current": "stella", "new": "nueva-clave"}, headers=h)
    assert resp.status_code == 200
    assert ctx.config.get("web.default_password") is False
    old = ctx.config.get("api.token")
    new = client.post("/api/v1/auth/token", headers=h).get_json()["token"]
    assert new != old and ctx.config.get("api.token") == new
    client.post("/logout", data={"csrf": csrf})
    assert login(client, "nueva-clave")[0].status_code == 302


def test_login_redirect_is_local_only(client):
    resp = client.post("/login?next=//evil.example", data={"username": "admin", "password": "stella"})
    assert resp.headers["Location"].endswith("/")


def test_static_assets_are_versioned_by_content(client, tmp_path):
    from stella.web import asset_version

    (tmp_path / "app.js").write_text("a")
    (tmp_path / "app.css").write_text("b")
    v1 = asset_version(str(tmp_path))
    (tmp_path / "app.js").write_text("a2")
    assert asset_version(str(tmp_path)) != v1
    login(client)
    page = client.get("/").get_data(as_text=True)
    assert "app.js?v=" in page and "?v=2.0.0" not in page
