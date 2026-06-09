import hashlib
import hmac
import logging
import os
import sqlite3
import sys
from functools import wraps
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse
from urllib.request import urlopen
import socket
from flask import Flask, g, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

app = Flask(__name__)

BASE_DIR = os.path.dirname(__file__)


def load_dotenv_file(path):
    if not os.path.exists(path):
        return

    with open(path, encoding="utf-8") as env_file:
        for line in env_file:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip("'\"")
            os.environ.setdefault(key, value)


load_dotenv_file(os.path.join(BASE_DIR, ".env"))

# Keep secrets out of the source tree; Docker and local runs inject these from .env.
DATABASE = os.environ.get("DATABASE_PATH", os.path.join(BASE_DIR, "ikt_portal.db"))
app.secret_key = os.environ.get("SECRET_KEY", "")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
ADMIN_PASSWORD_HASH = os.environ.get("ADMIN_PASSWORD_HASH", "")
TICKET_HASH_SALT = os.environ.get("TICKET_HASH_SALT", app.secret_key or "ikt-portalen-local-salt")

STATUS_OPTIONS = {
    "open": "Åpen",
    "in_progress": "Under arbeid",
    "solved": "Løst",
}

PRIORITY_OPTIONS = {
    "low": "Lav",
    "medium": "Middels",
    "high": "Høy",
}

CATEGORY_OPTIONS = {
    "network": "Nettverk",
    "account": "Konto",
    "software": "Programvare",
    "hardware": "Maskinvare",
    "other": "Annet",
}

LAST_HEALTH_CHECK = {
    "status": "unknown",
    "app": "unknown",
    "database": "unknown",
    "service": "ikt-portalen",
    "checked_at": None,
}


# ---------------------------------------------------------------------------
# Template context processor – makes `now` available in all templates
# ---------------------------------------------------------------------------

@app.context_processor
def inject_now():
    return {
        "now": datetime.now(timezone.utc),
        "status_options": STATUS_OPTIONS,
        "priority_options": PRIORITY_OPTIONS,
        "category_options": CATEGORY_OPTIONS,
    }


def configure_logging():
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    if not any(isinstance(existing_handler, logging.StreamHandler) for existing_handler in app.logger.handlers):
        app.logger.addHandler(handler)

    app.logger.setLevel(logging.INFO)
    logging.getLogger("werkzeug").setLevel(logging.INFO)


def admin_required(view):
    # Protect admin-only pages with a simple session flag set at login.
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect(url_for("admin_login", next=request.path))
        return view(*args, **kwargs)

    return wrapped_view


def is_safe_redirect_target(target):
    if not target:
        return False
    # Prevent open-redirects by only allowing URLs on this same host.
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


def normalize_choice(value, allowed_values, default_value):
    if value in allowed_values:
        return value
    return default_value


def verify_admin_password(password):
    if ADMIN_PASSWORD_HASH:
        return check_password_hash(ADMIN_PASSWORD_HASH, password)
    if ADMIN_PASSWORD:
        return hmac.compare_digest(password, ADMIN_PASSWORD)
    return False


def hash_ticket_value(value):
    normalized_value = value.strip().lower()
    digest_input = f"{TICKET_HASH_SALT}:{normalized_value}".encode("utf-8")
    return hashlib.sha256(digest_input).hexdigest()


def format_health_timestamp(timestamp):
    return timestamp.strftime("%m/%d %H:%M")


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


def check_database_health():
    try:
        with sqlite3.connect(DATABASE) as db:
            db.execute("SELECT 1").fetchone()
        return True
    except Exception as exc:
        app.logger.error("Health check failed: database unavailable (%s)", exc)
        return False


def build_health_report():
    database_ok = check_database_health()
    checked_at = datetime.now().astimezone()
    report = {
        "status": "ok" if database_ok else "error",
        "app": "ok",
        "database": "ok" if database_ok else "error",
        "service": "ikt-portalen",
        "checked_at": format_health_timestamp(checked_at),
        "checked_at_iso": checked_at.astimezone(timezone.utc).isoformat(),
    }
    LAST_HEALTH_CHECK.update(report)
    return report


def get_ticket_summary():
    db = get_db()
    return db.execute(
        """
        SELECT
            COUNT(*) AS total,
            COALESCE(SUM(status = 'open'), 0) AS open_count,
            COALESCE(SUM(status = 'in_progress'), 0) AS in_progress_count,
            COALESCE(SUM(status = 'solved'), 0) AS solved_count,
            COALESCE(SUM(priority = 'high'), 0) AS high_priority_count
        FROM tickets
        """
    ).fetchone()


def get_ticket_breakdown(column_name, values):
    db = get_db()
    breakdown = {}
    for value in values:
        row = db.execute(
            f"SELECT COUNT(*) AS count FROM tickets WHERE {column_name} = ?",
            (value,),
        ).fetchone()
        breakdown[value] = row["count"]
    return breakdown


def get_ticket_rows(status_filter):
    db = get_db()
    params = []
    where_clause = ""
    if status_filter and status_filter != "all":
        where_clause = "WHERE status = ?"
        params.append(status_filter)

    return db.execute(
        f"""
        SELECT id, navn, epost, navn_hash, epost_hash, problem, samtykke, status, priority, category, admin_notes, opprettet
        FROM tickets
        {where_clause}
        ORDER BY
            CASE status
                WHEN 'open' THEN 1
                WHEN 'in_progress' THEN 2
                WHEN 'solved' THEN 3
                ELSE 4
            END,
            CASE priority
                WHEN 'high' THEN 1
                WHEN 'medium' THEN 2
                WHEN 'low' THEN 3
                ELSE 4
            END,
            id DESC
        """,
        params,
    ).fetchall()


def get_metrics_snapshot():
    summary = get_ticket_summary()
    return {
        "service": "ikt-portalen",
        "tickets": {
            "total": summary["total"],
            "open": summary["open_count"],
            "in_progress": summary["in_progress_count"],
            "solved": summary["solved_count"],
            "high_priority": summary["high_priority_count"],
            "by_category": get_ticket_breakdown("category", CATEGORY_OPTIONS.keys()),
        },
        "health": LAST_HEALTH_CHECK,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def init_db():
    # Create the ticket table on first run; this is idempotent for deployment.
    db = sqlite3.connect(DATABASE)
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS tickets (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            navn      TEXT    NOT NULL,
            epost     TEXT    NOT NULL,
            navn_hash TEXT    NOT NULL DEFAULT '',
            epost_hash TEXT   NOT NULL DEFAULT '',
            problem   TEXT    NOT NULL,
            samtykke  INTEGER NOT NULL DEFAULT 0,
            status    TEXT    NOT NULL DEFAULT 'open',
            priority  TEXT    NOT NULL DEFAULT 'medium',
            category  TEXT    NOT NULL DEFAULT 'other',
            admin_notes TEXT   NOT NULL DEFAULT '',
            opprettet DATETIME DEFAULT (datetime('now','localtime'))
        )
        """
    )

    existing_columns = {row[1] for row in db.execute("PRAGMA table_info(tickets)").fetchall()}
    schema_updates = {
        "status": "TEXT NOT NULL DEFAULT 'open'",
        "priority": "TEXT NOT NULL DEFAULT 'medium'",
        "category": "TEXT NOT NULL DEFAULT 'other'",
        "admin_notes": "TEXT NOT NULL DEFAULT ''",
        "navn_hash": "TEXT NOT NULL DEFAULT ''",
        "epost_hash": "TEXT NOT NULL DEFAULT ''",
    }

    for column_name, column_definition in schema_updates.items():
        if column_name not in existing_columns:
            db.execute(f"ALTER TABLE tickets ADD COLUMN {column_name} {column_definition}")

    rows_missing_hashes = db.execute(
        """
        SELECT id, navn, epost
        FROM tickets
        WHERE navn_hash = '' OR epost_hash = ''
        """
    ).fetchall()
    for ticket_id, navn, epost in rows_missing_hashes:
        db.execute(
            "UPDATE tickets SET navn_hash = ?, epost_hash = ? WHERE id = ?",
            (hash_ticket_value(navn), hash_ticket_value(epost), ticket_id),
        )

    db.commit()
    db.close()


configure_logging()
init_db()


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
        priority = normalize_choice(request.form.get("priority", "medium"), PRIORITY_OPTIONS.keys(), "medium")
        category = normalize_choice(request.form.get("category", "other"), CATEGORY_OPTIONS.keys(), "other")

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
            cursor = db.execute(
                """
                INSERT INTO tickets (navn, epost, navn_hash, epost_hash, problem, samtykke, status, priority, category)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    navn,
                    epost,
                    hash_ticket_value(navn),
                    hash_ticket_value(epost),
                    problem,
                    1,
                    "open",
                    priority,
                    category,
                ),
            )
            db.commit()
            app.logger.info(
                "Ticket created: id=%s status=open priority=%s category=%s",
                cursor.lastrowid,
                priority,
                category,
            )
            return redirect(url_for("success"))

    return render_template("ticket.html", errors=errors)


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    error = None
    next_page = request.args.get("next") or request.form.get("next") or url_for("tickets")

    if request.method == "POST":
        password = request.form.get("password", "")
        if not ADMIN_PASSWORD_HASH and not ADMIN_PASSWORD:
            app.logger.error("Admin login blocked because ADMIN_PASSWORD is not configured")
            error = "Admin-passord er ikke konfigurert på serveren."
        elif verify_admin_password(password):
            session["is_admin"] = True
            app.logger.info("Admin login success from %s", request.remote_addr or "unknown")
            if not is_safe_redirect_target(next_page):
                next_page = url_for("tickets")
            return redirect(next_page)
        else:
            app.logger.warning("Admin login failed from %s", request.remote_addr or "unknown")
            error = "Ugyldig passord."

    return render_template("admin_login.html", error=error, next_page=next_page)


@app.route("/admin/logout")
def admin_logout():
    session.pop("is_admin", None)
    return redirect(url_for("index"))


@app.route("/admin/health")
@admin_required
def admin_health():
    health_report = build_health_report()
    metrics_snapshot = get_metrics_snapshot()
    return render_template(
        "admin_health.html",
        health=health_report,
        metrics=metrics_snapshot,
        raw_health_url=url_for("health"),
        raw_metrics_url=url_for("metrics"),
        dashboard_url=url_for("tickets"),
    )


@app.route("/tickets")
@admin_required
def tickets():
    status_filter = request.args.get("status", "all")
    if status_filter not in {"all", *STATUS_OPTIONS.keys()}:
        status_filter = "all"

    summary = get_ticket_summary()
    rows = get_ticket_rows(status_filter)
    health = build_health_report()
    grafana_url = os.environ.get("GRAFANA_URL", "https://grafana.example.local")

    return render_template(
        "tickets.html",
        tickets=rows,
        summary=summary,
        health=health,
        status_filter=status_filter,
        grafana_url=grafana_url,
        metrics_url=url_for("metrics"),
    )


@app.route("/tickets/status/<int:ticket_id>", methods=["POST"])
@admin_required
def change_ticket_status(ticket_id):
    new_status = normalize_choice(request.form.get("status", "open"), STATUS_OPTIONS.keys(), "open")
    db = get_db()
    db.execute("UPDATE tickets SET status = ? WHERE id = ?", (new_status, ticket_id))
    db.commit()
    app.logger.info("Ticket status changed: id=%s status=%s", ticket_id, new_status)
    return redirect(url_for("tickets", status=request.args.get("status", "all")))


@app.route("/tickets/notes/<int:ticket_id>", methods=["POST"])
@admin_required
def update_ticket_notes(ticket_id):
    admin_notes = request.form.get("admin_notes", "").strip()
    db = get_db()
    db.execute("UPDATE tickets SET admin_notes = ? WHERE id = ?", (admin_notes, ticket_id))
    db.commit()
    app.logger.info("Ticket notes updated: id=%s", ticket_id)
    return redirect(url_for("tickets", status=request.args.get("status", "all")))


@app.route("/tickets/delete/<int:ticket_id>", methods=["POST"])
@admin_required
def delete_ticket(ticket_id):
    # Admin-only hard delete for support tickets.
    db = get_db()
    db.execute("DELETE FROM tickets WHERE id = ?", (ticket_id,))
    db.commit()
    app.logger.info("Ticket deleted: id=%s", ticket_id)
    return redirect(url_for("tickets"))


@app.route("/health")
def health():
    report = build_health_report()
    status_code = 200 if report["status"] == "ok" else 503
    return jsonify(report), status_code


@app.route("/metrics")
@admin_required
def metrics():
    return jsonify(get_metrics_snapshot())


@app.route("/success")
def success():
    return render_template("success.html")


@app.route("/brukerveiledninger")
def brukerveiledninger():
    return render_template("brukerveiledninger.html")


@app.route("/driftsstatus")
def driftsstatus():
    # Each entry either runs a live check or falls back to a static status.
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
    debug_mode = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(debug=debug_mode, host="0.0.0.0", port=5000)
