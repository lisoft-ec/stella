"""Flask web interface and REST API."""
import datetime
import hashlib
import os
import hmac
import secrets

from flask import Flask, g, jsonify, redirect, request, session, url_for

PUBLIC_ENDPOINTS = ("views.login", "static")


def asset_version(static_dir):
    """Short hash of app.js/app.css contents: any change forces browsers to download them again."""
    digest = hashlib.sha256()
    for name in ("app.js", "app.css"):
        try:
            with open(os.path.join(static_dir, name), "rb") as fh:
                digest.update(fh.read())
        except OSError:
            pass
    return digest.hexdigest()[:10]


def create_app(ctx):
    """``ctx`` is the running :class:`stella.app.App`."""
    from .api import api
    from .views import views

    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=ctx.config.get("web.secret_key"),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        PERMANENT_SESSION_LIFETIME=datetime.timedelta(days=7),
        SEND_FILE_MAX_AGE_DEFAULT=3600,
    )
    app.extensions["stella"] = ctx
    assets = asset_version(app.static_folder)
    app.register_blueprint(views)
    app.register_blueprint(api, url_prefix="/api/v1")

    @app.before_request
    def authenticate():
        g.ctx = ctx
        g.via_token = False
        ctx.network.touch_web()
        if request.endpoint in PUBLIC_ENDPOINTS:
            return None
        token = ctx.config.get("api.token")
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer ") and token and hmac.compare_digest(auth[7:].strip(), token):
            g.via_token = True
            return None
        if session.get("user"):
            if request.method not in ("GET", "HEAD", "OPTIONS"):
                sent = request.headers.get("X-CSRF-Token") or request.form.get("csrf", "")
                if not hmac.compare_digest(sent, session.get("csrf", "")):
                    return jsonify(error="Token CSRF no válido"), 403
            return None
        if request.path.startswith("/api/") or request.path.endswith(".mjpg"):
            return jsonify(error="No autorizado"), 401
        return redirect(url_for("views.login", next=request.path))

    @app.context_processor
    def inject_globals():
        if "csrf" not in session:
            session["csrf"] = secrets.token_urlsafe(24)
        from .. import __version__
        return {
            "csrf_token": session["csrf"],
            "version": __version__,
            "assets": assets,
            "device_name": ctx.config.get("device.name"),
            "device_id": ctx.config.get("device.id"),
            "default_password": bool(ctx.config.get("web.default_password")),
            "network_managed": bool(ctx.config.get("network.managed")),
        }

    @app.after_request
    def security_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        return resp

    return app
