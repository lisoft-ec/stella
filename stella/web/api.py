"""REST API ``/api/v1`` (Bearer token or web session)."""
import json
import secrets
import time

from flask import Blueprint, Response, abort, g, jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

from ..config import PASSWORD_METHOD, ConfigError, redact
from ..hw import system

api = Blueprint("api", __name__)

# Sections that can be edited through PUT /config/<section>.
EDITABLE = ("device", "camera", "detector", "motion", "tracking", "counting", "mqtt",
            "webhook", "network", "leds", "ota", "web")
# Keys of the "web" section that must go through dedicated endpoints.
WEB_PROTECTED = ("password_hash", "secret_key", "default_password", "username")


def body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, "Se espera un objeto JSON")
    return data


@api.errorhandler(400)
@api.errorhandler(404)
@api.errorhandler(503)
def http_error(err):
    return jsonify(error=getattr(err, "description", str(err))), err.code


@api.errorhandler(ConfigError)
def config_error(err):
    return jsonify(error=str(err)), 400


def session_only():
    if g.via_token:
        abort(403, "Solo disponible desde la interfaz web")


# -- status / counters / events ----------------------------------------------
@api.route("/status")
def status():
    return jsonify(g.ctx.status())


@api.route("/counters")
def counters():
    return jsonify(g.ctx.counters.state())


@api.route("/counters/reset", methods=["POST"])
def counters_reset():
    data = request.get_json(silent=True) or {}
    try:
        occupancy = int(data.get("occupancy", 0) or 0)
    except (TypeError, ValueError):
        abort(400, "occupancy debe ser un entero")
    return jsonify(g.ctx.reset_counters(occupancy))


@api.route("/events")
def events():
    since = request.args.get("since_id", 0, type=int)
    limit = min(1000, max(1, request.args.get("limit", 100, type=int)))
    return jsonify(g.ctx.storage.events(since, limit))


@api.route("/stream")
def stream():
    """Server-sent events: pipeline snapshot + counters (~5 per second)."""
    ctx = g.ctx

    def generate():
        seq = 0
        last_event_seq = -1
        last_sent = 0.0
        while True:
            seq, snap = ctx.pipeline.wait_snapshot(seq, 1.0)
            now = time.monotonic()
            if now - last_sent < 0.2:
                time.sleep(0.2 - (now - last_sent))
            last_sent = time.monotonic()
            event_seq, event = ctx.last_event()
            msg = {"pipeline": snap, "counters": ctx.counters.state()}
            if event_seq != last_event_seq:
                last_event_seq = event_seq
                msg["event"] = event
            yield "data: %s\n\n" % json.dumps(msg)

    resp = Response(generate(), mimetype="text/event-stream")
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["X-Accel-Buffering"] = "no"
    return resp


# -- configuration --------------------------------------------------------------
@api.route("/config")
def config_all():
    return jsonify(redact(g.ctx.config.snapshot()))


@api.route("/config/<section>")
def config_get(section):
    data = redact(g.ctx.config.snapshot())
    if section not in data:
        abort(404, "Sección desconocida")
    return jsonify(data[section])


@api.route("/config/<section>", methods=["PUT"])
def config_put(section):
    if section not in EDITABLE:
        abort(404, "Sección no editable")
    values = body()
    if section == "web":
        values = {k: v for k, v in values.items() if k not in WEB_PROTECTED}
    if section == "device" and values.get("timezone") and not system.valid_timezone(values["timezone"]):
        abort(400, "Zona horaria desconocida")
    g.ctx.config.update_section(section, values)
    return jsonify(redact(g.ctx.config.snapshot())[section])


@api.route("/timezones")
def timezones():
    return jsonify(system.timezones())


# -- auth -----------------------------------------------------------------------
@api.route("/auth/password", methods=["POST"])
def change_password():
    session_only()
    data = body()
    cfg = g.ctx.config
    if not check_password_hash(cfg.get("web.password_hash"), str(data.get("current", ""))):
        abort(400, "La contraseña actual no es correcta")
    new = str(data.get("new", ""))
    if len(new) < 8:
        abort(400, "La nueva contraseña debe tener al menos 8 caracteres")
    values = {"password_hash": generate_password_hash(new, method=PASSWORD_METHOD), "default_password": False}
    username = str(data.get("username", "")).strip()
    if username:
        values["username"] = username
    cfg.update_section("web", values, notify=False)
    session["user"] = cfg.get("web.username")
    return jsonify(ok=True)


@api.route("/auth/token")
def get_token():
    session_only()
    return jsonify(token=g.ctx.config.get("api.token"))


@api.route("/auth/token", methods=["POST"])
def regenerate_token():
    session_only()
    token = secrets.token_urlsafe(32)
    g.ctx.config.update_section("api", {"token": token}, notify=False)
    return jsonify(token=token)


# -- integration tests ---------------------------------------------------------------
@api.route("/test/mqtt", methods=["POST"])
def test_mqtt():
    from ..config import deep_merge, unmask

    cfg = g.ctx.config.section("mqtt")
    cfg = deep_merge(cfg, unmask(body(), cfg))
    ok, message = g.ctx.mqtt.test(cfg, g.ctx.config.get("device.id"))
    return jsonify(ok=ok, message=message)


@api.route("/test/webhook", methods=["POST"])
def test_webhook():
    from ..config import deep_merge

    cfg = deep_merge(g.ctx.config.section("webhook"), body())
    if not str(cfg.get("url", "")).startswith(("http://", "https://")):
        abort(400, "URL no válida")
    ok, message = g.ctx.webhook.test(cfg, g.ctx.config.get("device.id"))
    return jsonify(ok=ok, message=message)


# -- system ----------------------------------------------------------------------
@api.route("/system/restart", methods=["POST"])
def restart():
    import threading

    service = g.ctx.config.get("ota.service", "stella")
    threading.Thread(target=system.restart_service, args=(service, 1.0), daemon=True).start()
    return jsonify(ok=True, message="Reiniciando Stella…")


@api.route("/system/reboot", methods=["POST"])
def reboot():
    try:
        system.reboot()
    except RuntimeError as exc:
        abort(400, str(exc))
    return jsonify(ok=True, message="Reiniciando el equipo…")


@api.route("/system/factory-reset", methods=["POST"])
def factory_reset():
    import threading

    from ..factory import CONFIRM_WORD

    session_only()
    if body().get("confirm") != CONFIRM_WORD:
        abort(400, "Escribe %s para confirmar" % CONFIRM_WORD)
    ctx = g.ctx

    def run():
        time.sleep(1.0)  # let the HTTP response go out first
        ctx.factory_reset()

    threading.Thread(target=run, name="factory-reset", daemon=True).start()
    hotspot = ctx.config.get("network.managed")
    message = "Restaurando la configuración de fábrica. Stella se reiniciará"
    if hotspot:
        message += "; en unos 2 minutos aparecerá la red wifi StellaWIFI (clave stella1234)"
    return jsonify(ok=True, message=message + ".")


@api.route("/leds/test", methods=["POST"])
def leds_test():
    data = body()
    leds = g.ctx.leds
    if data.get("sequence"):
        leds.test_sequence()
    else:
        color = data.get("color")
        if not (isinstance(color, list) and len(color) == 3):
            abort(400, "color debe ser [r, g, b]")
        seconds = min(10.0, max(0.5, float(data.get("seconds", 3))))
        leds.preview([int(bool(c)) for c in color], seconds)
    return jsonify(ok=True, driver=leds.driver)


@api.route("/network/status")
def network_status():
    from ..net.wifi import NmcliError

    try:
        return jsonify(g.ctx.network.status())
    except NmcliError as exc:
        abort(503, "NetworkManager: %s" % exc)


@api.route("/network/scan")
def network_scan():
    from ..net.wifi import NmcliError

    if not g.ctx.network.managed():
        abort(400, "La gestión de red está desactivada")
    try:
        return jsonify(g.ctx.network.scan())
    except NmcliError as exc:
        abort(503, "NetworkManager: %s" % exc)


@api.route("/network/rescan", methods=["POST"])
def network_rescan():
    """With the hotspot up: drop it ~20 s to scan for real (the client must reconnect)."""
    if not g.ctx.network.managed():
        abort(400, "La gestión de red está desactivada")
    g.ctx.network.rescan_through_hotspot()
    return jsonify(ok=True, message="La red %s se cortará unos 20 segundos para buscar redes. "
                                    "Vuelve a conectarte y pulsa «Buscar»." % g.ctx.config.get("network.hotspot.ssid"))


@api.route("/ota")
def ota_state():
    return jsonify(g.ctx.ota.state())


@api.route("/ota/check", methods=["POST"])
def ota_check():
    from ..ota import OtaError

    try:
        return jsonify(g.ctx.ota.check())
    except OtaError as exc:
        abort(400, str(exc))


@api.route("/ota/apply", methods=["POST"])
def ota_apply():
    from ..ota import OtaError

    try:
        state = g.ctx.ota.apply()
    except OtaError as exc:
        abort(400, str(exc))
    return jsonify(dict(state, ok=True))


@api.route("/logs")
def logs():
    limit = min(400, max(1, request.args.get("limit", 200, type=int)))
    return jsonify(g.ctx.logs.lines(limit))
