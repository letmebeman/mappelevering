import sqlite3
import os
from datetime import datetime, timezone
from flask import Flask, render_template, request, redirect, url_for, g

app = Flask(__name__)

DATABASE = os.path.join(os.path.dirname(__file__), "ikt_portal.db")


# ---------------------------------------------------------------------------
# Template context processor – makes `now` available in all templates
# ---------------------------------------------------------------------------

@app.context_processor
def inject_now():
    return {"now": datetime.now(timezone.utc)}


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


@app.route("/success")
def success():
    return render_template("success.html")


@app.route("/brukerveiledninger")
def brukerveiledninger():
    return render_template("brukerveiledninger.html")


@app.route("/driftsstatus")
def driftsstatus():
    services = [
        {"navn": "E-post (Outlook / Exchange)", "status": "ok",      "melding": "Normal drift"},
        {"navn": "Internett / VPN",              "status": "ok",      "melding": "Normal drift"},
        {"navn": "Filserver (\\\\filserver)",      "status": "ok",      "melding": "Normal drift"},
        {"navn": "Skriver (etg. 2)",              "status": "advarsel","melding": "Planlagt vedlikehold 20. mai kl. 08–10"},
        {"navn": "Teams / Video",                 "status": "ok",      "melding": "Normal drift"},
    ]
    return render_template("driftsstatus.html", services=services)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    init_db()
    debug_mode = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(debug=debug_mode, host="0.0.0.0", port=5000)
