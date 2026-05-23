import sqlite3
import os
from functools import wraps
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse
from urllib.request import urlopen
import socket
from flask import Flask, render_template, request, redirect, url_for, g, session

app = Flask(__name__)

DATABASE = os.path.join(os.path.dirname(__file__), "ikt_portal.db")
app.secret_key = os.environ.get("SECRET_KEY", "yo-im-secret")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")


# ---------------------------------------------------------------------------
# Template context processor – makes `now` available in all templates
# ---------------------------------------------------------------------------

@app.context_processor
def inject_now():
    return {"now": datetime.now(timezone.utc)}


def admin_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect(url_for("admin_login", next=request.path))
        return view(*args, **kwargs)

    return wrapped_view


def is_safe_redirect_target(target):
    if not target:
        return False
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in {"http", "https"} and test_url.netloc == urlparse(request.host_url).netloc


def check_http_target(url, timeout=2):
    try:
        with urlopen(url, timeout=timeout) as response:
            return response.status < 400, f"HTTP {response.status}"
    except Exception:
        return False, "Ute av drift"


def check_tcp_target(host, port, timeout=2):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, "Tjenesten svarer"
    except Exception:
        return False, "Ute av drift"


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db


@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, "_database", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DATABASE)
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS tickets (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            navn      TEXT    NOT NULL,
            epost     TEXT    NOT NULL,
            problem   TEXT    NOT NULL,
            samtykke  INTEGER NOT NULL DEFAULT 0,
            opprettet DATETIME DEFAULT (datetime('now','localtime'))
        )
        """
    )
    db.commit()
    db.close()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/ticket", methods=["GET", "POST"])
def ticket():
    errors = {}
    if request.method == "POST":
        navn = request.form.get("navn", "").strip()
        epost = request.form.get("epost", "").strip()
        problem = request.form.get("problem", "").strip()
        samtykke = request.form.get("samtykke")

        if not navn:
            errors["navn"] = "Navn er påkrevd."
        if not epost or "@" not in epost:
            errors["epost"] = "Skriv inn en gyldig e-postadresse."
        if not problem:
            errors["problem"] = "Beskriv problemet ditt."
        if not samtykke:
            errors["samtykke"] = "Du må godta lagring av opplysninger for å sende inn saken."

        if not errors:
            db = get_db()
            db.execute(
                "INSERT INTO tickets (navn, epost, problem, samtykke) VALUES (?, ?, ?, ?)",
                (navn, epost, problem, 1),
            )
            db.commit()
            return redirect(url_for("success"))

    return render_template("ticket.html", errors=errors)


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    error = None
    next_page = request.args.get("next") or request.form.get("next") or url_for("tickets")

    if request.method == "POST":
        password = request.form.get("password", "")
        if password == ADMIN_PASSWORD:
            session["is_admin"] = True
            if not is_safe_redirect_target(next_page):
                next_page = url_for("tickets")
            return redirect(next_page)
        error = "Ugyldig passord."

    return render_template("admin_login.html", error=error, next_page=next_page)


@app.route("/admin/logout")
def admin_logout():
    session.pop("is_admin", None)
    return redirect(url_for("index"))


@app.route("/tickets")
@admin_required
def tickets():
    db = get_db()
    rows = db.execute(
        """
        SELECT id, navn, epost, problem, samtykke, opprettet
        FROM tickets
        ORDER BY id DESC
        """
    ).fetchall()
    return render_template("tickets.html", tickets=rows)


@app.route("/success")
def success():
    return render_template("success.html")


@app.route("/brukerveiledninger")
def brukerveiledninger():
    return render_template("brukerveiledninger.html")


@app.route("/driftsstatus")
def driftsstatus():
    service_checks = [
        {
            "navn": "E-post (Outlook / Exchange)",
            "type": "http",
            "target": os.environ.get("DRIFTSSTATUS_EMAIL_URL"),
            "fallback": {"status": "ok", "melding": "Normal drift"},
        },
        {
            "navn": "Internett / VPN",
            "type": "tcp",
            "host": os.environ.get("DRIFTSSTATUS_VPN_HOST"),
            "port": int(os.environ.get("DRIFTSSTATUS_VPN_PORT", "0") or "0"),
            "fallback": {"status": "ok", "melding": "Normal drift"},
        },
        {
            "navn": "Filserver (\\\\filserver)",
            "type": "tcp",
            "host": os.environ.get("DRIFTSSTATUS_FILESERVER_HOST"),
            "port": int(os.environ.get("DRIFTSSTATUS_FILESERVER_PORT", "445") or "445"),
            "fallback": {"status": "ok", "melding": "Normal drift"},
        },
        {
            "navn": "Skriver (etg. 2)",
            "type": "tcp",
            "host": os.environ.get("DRIFTSSTATUS_PRINTER_HOST"),
            "port": int(os.environ.get("DRIFTSSTATUS_PRINTER_PORT", "9100") or "9100"),
            "fallback": {"status": "advarsel", "melding": "Planlagt vedlikehold 20. mai kl. 08–10"},
        },
        {
            "navn": "Teams / Video",
            "type": "http",
            "target": os.environ.get("DRIFTSSTATUS_TEAMS_URL"),
            "fallback": {"status": "ok", "melding": "Normal drift"},
        },
    ]

    services = []
    for service in service_checks:
        fallback = service["fallback"]
        if service["type"] == "http" and service.get("target"):
            is_up, message = check_http_target(service["target"])
            services.append({"navn": service["navn"], "status": "ok" if is_up else "feil", "melding": message})
        elif service["type"] == "tcp" and service.get("host") and service.get("port"):
            is_up, message = check_tcp_target(service["host"], service["port"])
            services.append({"navn": service["navn"], "status": "ok" if is_up else "feil", "melding": message})
        else:
            services.append({"navn": service["navn"], **fallback})
    return render_template("driftsstatus.html", services=services)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    init_db()
    debug_mode = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(debug=debug_mode, host="0.0.0.0", port=5000)
