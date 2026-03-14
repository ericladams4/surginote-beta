import json
import os
from functools import wraps
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, session, redirect, url_for
from openai import OpenAI

from parser import build_case_facts
from prompt_builder import build_prompt
from config import PUBLIC_WARNING, PROCEDURE_LABELS

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-change-me")

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

BETA_PASSWORD = os.getenv("BETA_PASSWORD", "")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")


def require_beta_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get("beta_authed"):
            return f(*args, **kwargs)
        return redirect(url_for("login"))
    return decorated


def require_admin_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get("admin_authed"):
            return f(*args, **kwargs)
        return redirect(url_for("admin_login"))
    return decorated


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        if request.form.get("password") == BETA_PASSWORD:
            session["beta_authed"] = True
            return redirect(url_for("index"))
        error = "Incorrect password"
    return render_template("login.html", error=error, mode="beta")


@app.route("/admin-login", methods=["GET", "POST"])
def admin_login():
    error = None
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASSWORD:
            session["admin_authed"] = True
            return redirect(url_for("admin"))
        error = "Incorrect password"
    return render_template("login.html", error=error, mode="admin")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@require_beta_auth
def index():
    return render_template("index.html", warning=PUBLIC_WARNING)


@app.route("/admin")
@require_admin_auth
def admin():
    return render_template("admin.html")


@app.route("/healthz")
def healthz():
    return jsonify({"status": "ok"})


@app.route("/generate-note", methods=["POST"])
@require_beta_auth
def generate_note():
    payload = request.get_json(silent=True) or {}
    shorthand = payload.get("shorthand", "").strip()

    if not shorthand:
        return jsonify({"error": "No shorthand provided"}), 400

    if not os.getenv("OPENAI_API_KEY"):
        return jsonify({"error": "Missing OPENAI_API_KEY environment variable"}), 500

    case_facts = build_case_facts(shorthand)
    prompt = build_prompt(case_facts)

    response = client.responses.create(
        model="gpt-5-mini",
        input=prompt,
    )

    note_text = response.output_text

    procedure_key = case_facts.get("procedure")
    procedure_label = PROCEDURE_LABELS.get(procedure_key, "Unknown")

    return jsonify(
        {
            "note": note_text,
            "case_facts": case_facts,
            "procedure_label": procedure_label,
        }
    )


@app.route("/feedback", methods=["POST"])
@require_beta_auth
def feedback():
    payload = request.get_json(silent=True) or {}
    record = {
        "shorthand": payload.get("shorthand", ""),
        "procedure": payload.get("procedure", ""),
        "rating": payload.get("rating", ""),
        "comment": payload.get("comment", ""),
    }

    outpath = DATA_DIR / "feedback.jsonl"
    with open(outpath, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")

    return jsonify({"status": "ok"})


@app.route("/admin/save-example", methods=["POST"])
@require_admin_auth
def save_example():
    payload = request.get_json(silent=True) or {}
    record = {
        "procedure": payload.get("procedure"),
        "shorthand_input": payload.get("shorthand_input"),
        "ideal_note": payload.get("ideal_note"),
        "tags": payload.get("tags", []),
    }

    outpath = DATA_DIR / "examples.jsonl"
    with open(outpath, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")

    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(debug=True, port=5001)
