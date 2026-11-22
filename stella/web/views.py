"""HTML pages, login and video stream."""
import hmac
import secrets
import time

from flask import Blueprint, Response, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

views = Blueprint("views", __name__)

PAGES = [
    ("views.dashboard", "Panel"),
    ("views.calibration", "Calibración"),
    ("views.network", "Red"),
    ("views.integrations", "Integraciones"),
    ("views.system_page", "Sistema"),
]


@views.app_context_processor
def nav():
    return {"pages": PAGES}


@views.route("/login", methods=["GET", "POST"])
def login():
    from flask import current_app

    ctx = current_app.extensions["stella"]
    error = None
    if request.method == "POST":
        user = request.form.get("username", "")
        password = request.form.get("password", "")
        ok_user = hmac.compare_digest(user, ctx.config.get("web.username", ""))
        ok_pass = check_password_hash(ctx.config.get("web.password_hash", ""), password)
        if ok_user and ok_pass:
            session.clear()
            session.permanent = True
            session["user"] = user
            session["csrf"] = secrets.token_urlsafe(24)
            target = request.args.get("next", "")
            if not target.startswith("/") or target.startswith("//"):
                target = url_for("views.dashboard")
            return redirect(target)
        time.sleep(1.0)
        error = "Usuario o contraseña incorrectos"
    return render_template("login.html", error=error)


@views.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("views.login"))


@views.route("/")
def dashboard():
    return render_template("dashboard.html", page="views.dashboard")


@views.route("/calibracion")
def calibration():
    return render_template("calibration.html", page="views.calibration")


@views.route("/red")
def network():
    return render_template("network.html", page="views.network")


@views.route("/integraciones")
def integrations():
    return render_template("integrations.html", page="views.integrations")


@views.route("/sistema")
def system_page():
    return render_template("system.html", page="views.system_page")


@views.route("/video.mjpg")
def video():
    pipeline = g.ctx.pipeline

    def frames():
        seq = 0
        while True:
            seq, jpeg = pipeline.wait_jpeg(seq, 2.0)
            if jpeg is None:
                continue
            yield (b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: " +
                   str(len(jpeg)).encode() + b"\r\n\r\n" + jpeg + b"\r\n")

    resp = Response(frames(), mimetype="multipart/x-mixed-replace; boundary=frame")
    resp.headers["Cache-Control"] = "no-store"
    return resp
