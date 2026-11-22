import os
import stat

import pytest
import yaml

from stella.config import SECRET_MASK, Config, ConfigError, redact


@pytest.fixture
def cfg(tmp_path):
    return Config(str(tmp_path / "config.yaml")).load()


def test_first_load_creates_file_with_secrets(cfg):
    assert os.path.exists(cfg.path)
    assert stat.S_IMODE(os.stat(cfg.path).st_mode) == 0o600
    assert cfg.get("api.token")
    assert cfg.get("web.secret_key")
    assert cfg.get("web.password_hash").startswith(("pbkdf2:", "scrypt:"))
    assert cfg.get("web.default_password") is True


def test_partial_file_is_merged_with_defaults(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump({"camera": {"source": "0", "width": 1280}}))
    cfg = Config(str(path)).load()
    assert cfg.get("camera.source") == 0
    assert cfg.get("camera.width") == 1280
    assert cfg.get("camera.height") == 480


def test_update_section_validates_and_persists(cfg):
    cfg.update_section("counting", {"line": [[0.1, 0.2], [0.9, 0.2]]})
    reloaded = Config(cfg.path).load()
    assert reloaded.get("counting.line") == [[0.1, 0.2], [0.9, 0.2]]
    with pytest.raises(ConfigError):
        cfg.update_section("counting", {"line": [[0.1, 0.2], [0.1, 0.2]]})
    with pytest.raises(ConfigError):
        cfg.update_section("counting", {"roi": [[0, 0], [2, 0], [1, 1]]})
    # Invalid update does not change the stored value.
    assert cfg.get("counting.line") == [[0.1, 0.2], [0.9, 0.2]]


def test_redact_and_unmask_keep_secrets(cfg):
    cfg.update_section("mqtt", {"password": "secreto"})
    cfg.update_section("network", {"wifi": [{"ssid": "Casa", "password": "clave-larga"}]})
    red = redact(cfg.snapshot())
    assert red["mqtt"]["password"] == SECRET_MASK
    assert red["network"]["wifi"][0]["password"] == SECRET_MASK
    assert red["api"]["token"] == SECRET_MASK
    # Client sends back masked values: stored secrets are preserved.
    cfg.update_section("mqtt", {"password": SECRET_MASK, "host": "broker"})
    cfg.update_section("network", {"wifi": red["network"]["wifi"] + [{"ssid": "Otra", "password": ""}]})
    assert cfg.get("mqtt.password") == "secreto"
    assert cfg.get("mqtt.host") == "broker"
    assert cfg.get("network.wifi")[0]["password"] == "clave-larga"
    assert len(cfg.get("network.wifi")) == 2


def test_change_listener_called(cfg):
    seen = []
    cfg.on_change(seen.append)
    cfg.update_section("webhook", {"timeout": 3})
    assert seen == ["webhook"]


def test_hotspot_password_is_not_masked(cfg):
    red = redact(cfg.snapshot())
    assert red["network"]["hotspot"]["password"] == cfg.get("network.hotspot.password")
