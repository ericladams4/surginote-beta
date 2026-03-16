import os
import re
from functools import wraps
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, session, redirect, url_for
from openai import OpenAI, RateLimitError

from parser import build_case_facts
from prompt_builder import build_prompt
from config import PUBLIC_WARNING, PROCEDURE_LABELS
from db import init_db, get_conn

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-change-me")

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

BETA_PASSWORD = os.getenv("BETA_PASSWORD", "")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")

ALLOWED_NOTE_TYPES = {"op_note", "clinic_note", "consult_note"}

init_db()


def require_beta_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get("beta_authed"):
            return f(*args, **kwargs)
        return redirect(url_for("login"))
    return decorated


def require_user_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("beta_authed"):
            return redirect(url_for("login"))
        if not session.get("phone_authed"):
            return redirect(url_for("phone_login"))
        return f(*args, **kwargs)
    return decorated


def require_admin_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get("admin_authed"):
            return f(*args, **kwargs)
        return redirect(url_for("admin_login"))
    return decorated


def normalize_phone(phone: str) -> str:
    phone = (phone or "").strip()

    if phone.startswith("+"):
        digits = re.sub(r"\D", "", phone)
        return f"+{digits}" if digits else ""

    digits = re.sub(r"\D", "", phone)
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"

    return ""


def get_or_create_user(phone: str):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT id, phone FROM users WHERE phone = ?", (phone,))
    user = cur.fetchone()

    if not user:
        cur.execute("INSERT INTO users (phone) VALUES (?)", (phone,))
        conn.commit()
        cur.execute("SELECT id, phone FROM users WHERE phone = ?", (phone,))
        user = cur.fetchone()

    conn.close()
    return user


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        if request.form.get("password") == BETA_PASSWORD:
            session["beta_authed"] = True
            return redirect(url_for("phone_login"))
        error = "Incorrect password"
    return render_template("login.html", error=error, mode="beta")


@app.route("/phone-login")
@require_beta_auth
def phone_login():
    if session.get("phone_authed"):
        return redirect(url_for("index"))
    return render_template("phone_login.html")


@app.route("/auth/phone-login", methods=["POST"])
@require_beta_auth
def phone_login_direct():
    payload = request.get_json(silent=True) or {}
    phone = normalize_phone(payload.get("phone", ""))

    if not phone:
        return jsonify({"error": "Enter a valid phone number"}), 400

    user = get_or_create_user(phone)

    session["user_id"] = user["id"]
    session["phone"] = user["phone"]
    session["phone_authed"] = True

    return jsonify({"status": "ok", "redirect": url_for("index")})


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
    return redirect(url_for("landing"))


@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/app")
@require_user_auth
def index():
    return render_template("index.html", warning=PUBLIC_WARNING)


@app.route("/admin")
@require_admin_auth
def admin():
    return render_template("admin.html")


@app.route("/healthz")
def healthz():
    return jsonify({"status": "ok"})


@app.route("/request-access", methods=["POST"])
def request_access():
    payload = request.get_json(silent=True) or {}
    email = (payload.get("email") or "").strip().lower()

    if not email:
        return jsonify({"error": "Email is required"}), 400

    if "@" not in email or "." not in email:
        return jsonify({"error": "Enter a valid email"}), 400

    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO access_requests (email) VALUES (?)",
            (email,)
        )
        conn.commit()
        conn.close()
        return jsonify({"status": "ok"})
    except Exception:
        return jsonify({"status": "ok"})


@app.route("/api/templates/<note_type>", methods=["GET"])
@require_user_auth
def get_template(note_type):
    if note_type not in ALLOWED_NOTE_TYPES:
        return jsonify({"error": "Invalid note type"}), 400

    user_id = session["user_id"]

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, note_type, content, created_at, updated_at
        FROM templates
        WHERE user_id = ? AND note_type = ?
        """,
        (user_id, note_type)
    )
    row = cur.fetchone()
    conn.close()

    if not row:
        return jsonify({"template": None})

    return jsonify({
        "template": {
            "id": row["id"],
            "note_type": row["note_type"],
            "content": row["content"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
    })


@app.route("/api/templates/<note_type>", methods=["POST"])
@require_user_auth
def save_template(note_type):
    if note_type not in ALLOWED_NOTE_TYPES:
        return jsonify({"error": "Invalid note type"}), 400

    payload = request.get_json(silent=True) or {}
    content = (payload.get("content") or "").strip()

    if not content:
        return jsonify({"error": "Template content is required"}), 400

    user_id = session["user_id"]

    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO templates (user_id, note_type, content, updated_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(user_id, note_type)
        DO UPDATE SET content = excluded.content, updated_at = CURRENT_TIMESTAMP
        """,
        (user_id, note_type, content)
    )

    conn.commit()
    conn.close()

    return jsonify({"status": "ok"})


@app.route("/api/templates/<note_type>", methods=["DELETE"])
@require_user_auth
def delete_template(note_type):
    if note_type not in ALLOWED_NOTE_TYPES:
        return jsonify({"error": "Invalid note type"}), 400

    user_id = session["user_id"]

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM templates WHERE user_id = ? AND note_type = ?",
        (user_id, note_type)
    )
    conn.commit()
    conn.close()

    return jsonify({"status": "ok"})


@app.route("/generate-note", methods=["POST"])
@require_user_auth
def generate_note():
    payload = request.get_json(silent=True) or {}
    shorthand = payload.get("shorthand", "").strip()
    note_type = (payload.get("note_type") or "op_note").strip()

    if note_type not in ALLOWED_NOTE_TYPES:
        return jsonify({"error": "Invalid note type"}), 400

    if not shorthand:
        return jsonify({"error": "No shorthand provided"}), 400

    if not os.getenv("OPENAI_API_KEY"):
        return jsonify({"error": "Missing OPENAI_API_KEY environment variable"}), 500

    case_facts = build_case_facts(shorthand)

    user_id = session["user_id"]
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT content FROM templates WHERE user_id = ? AND note_type = ?",
        (user_id, note_type)
    )
    row = cur.fetchone()
    conn.close()

    template_content = row["content"] if row else None

    prompt = build_prompt(
        case_facts=case_facts,
        note_type=note_type,
        template_content=template_content
    )

    try:
        response = client.responses.create(
            model="gpt-5-mini",
            input=prompt
        )
        note_text = response.output_text

    except RateLimitError:
        return jsonify({
            "error": "AI generation is temporarily unavailable. Please try again shortly."
        }), 503

    except Exception as e:
        return jsonify({
            "error": f"Generation failed: {str(e)}"
        }), 500

    procedure_key = case_facts.get("procedure")
    procedure_label = PROCEDURE_LABELS.get(procedure_key, "Unknown")

    return jsonify({
        "note": note_text,
        "case_facts": case_facts,
        "procedure_label": procedure_label,
        "note_type": note_type,
        "used_template": bool(template_content),
    })


@app.route("/feedback", methods=["POST"])
@require_user_auth
def feedback():
    payload = request.get_json(silent=True) or {}

    shorthand = payload.get("shorthand", "")
    procedure = payload.get("procedure", "")
    rating = payload.get("rating", "")
    comment = payload.get("comment", "")
    generated_note = payload.get("generated_note", "")

    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO feedback (shorthand, procedure, rating, comment, generated_note)
            VALUES (?, ?, ?, ?, ?)
            """,
            (shorthand, procedure, rating, comment, generated_note)
        )
        conn.commit()
        conn.close()
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": f"Unable to save feedback: {str(e)}"}), 500


@app.route("/admin/feedback")
@require_admin_auth
def admin_feedback():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, shorthand, procedure, rating, comment, generated_note, created_at
        FROM feedback
        ORDER BY created_at DESC
    """)
    rows = cur.fetchall()
    conn.close()

    return render_template("feedback_admin.html", feedback_rows=rows)


@app.route("/admin/access-requests")
@require_admin_auth
def admin_access_requests():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, email, created_at
        FROM access_requests
        ORDER BY created_at DESC
    """)
    rows = cur.fetchall()
    conn.close()

    return render_template("access_requests.html", requests=rows)


@app.route("/admin/sample-library")
@require_admin_auth
def sample_library():
    procedure_filter = (request.args.get("procedure") or "").strip()

    conn = get_conn()
    cur = conn.cursor()

    if procedure_filter:
        cur.execute(
            """
            SELECT id, procedure, title, shorthand_input, ideal_note, tags, created_at
            FROM procedure_samples
            WHERE procedure = ?
            ORDER BY created_at DESC
            """,
            (procedure_filter,)
        )
    else:
        cur.execute(
            """
            SELECT id, procedure, title, shorthand_input, ideal_note, tags, created_at
            FROM procedure_samples
            ORDER BY created_at DESC
            """
        )

    rows = cur.fetchall()

    cur.execute("""
        SELECT DISTINCT procedure
        FROM procedure_samples
        WHERE procedure IS NOT NULL AND procedure != ''
        ORDER BY procedure ASC
    """)
    procedures = cur.fetchall()

    conn.close()

    return render_template(
        "sample_library.html",
        samples=rows,
        procedures=procedures,
        selected_procedure=procedure_filter
    )


@app.route("/admin/sample-library/<int:sample_id>/delete", methods=["POST"])
@require_admin_auth
def delete_sample(sample_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM procedure_samples WHERE id = ?", (sample_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("sample_library"))


@app.route("/admin/sample-library/<int:sample_id>/duplicate", methods=["POST"])
@require_admin_auth
def duplicate_sample(sample_id):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT procedure, title, shorthand_input, ideal_note, tags
        FROM procedure_samples
        WHERE id = ?
    """, (sample_id,))
    row = cur.fetchone()

    if not row:
        conn.close()
        return redirect(url_for("sample_library"))

    new_title = f"{row['title']} (copy)" if row["title"] else "Untitled sample (copy)"

    cur.execute("""
        INSERT INTO procedure_samples (procedure, title, shorthand_input, ideal_note, tags)
        VALUES (?, ?, ?, ?, ?)
    """, (
        row["procedure"],
        new_title,
        row["shorthand_input"],
        row["ideal_note"],
        row["tags"]
    ))

    conn.commit()
    conn.close()
    return redirect(url_for("sample_library"))


@app.route("/admin/sample-library/<int:sample_id>/edit", methods=["GET", "POST"])
@require_admin_auth
def edit_sample(sample_id):
    conn = get_conn()
    cur = conn.cursor()

    if request.method == "POST":
        procedure = (request.form.get("procedure") or "").strip()
        title = (request.form.get("title") or "").strip()
        shorthand_input = (request.form.get("shorthand_input") or "").strip()
        ideal_note = (request.form.get("ideal_note") or "").strip()
        tags = (request.form.get("tags") or "").strip()

        if not procedure or not shorthand_input or not ideal_note:
            cur.execute("""
                SELECT id, procedure, title, shorthand_input, ideal_note, tags, created_at
                FROM procedure_samples
                WHERE id = ?
            """, (sample_id,))
            row = cur.fetchone()
            conn.close()
            return render_template(
                "edit_sample.html",
                sample=row,
                error="Procedure, shorthand input, and ideal note are required."
            )

        cur.execute("""
            UPDATE procedure_samples
            SET procedure = ?, title = ?, shorthand_input = ?, ideal_note = ?, tags = ?
            WHERE id = ?
        """, (procedure, title, shorthand_input, ideal_note, tags, sample_id))
        conn.commit()
        conn.close()
        return redirect(url_for("sample_library"))

    cur.execute("""
        SELECT id, procedure, title, shorthand_input, ideal_note, tags, created_at
        FROM procedure_samples
        WHERE id = ?
    """, (sample_id,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return redirect(url_for("sample_library"))

    return render_template("edit_sample.html", sample=row, error=None)


@app.route("/admin/save-example", methods=["POST"])
@require_admin_auth
def save_example():
    payload = request.get_json(silent=True) or {}

    procedure = (payload.get("procedure") or "").strip()
    title = (payload.get("title") or "").strip()
    shorthand_input = (payload.get("shorthand_input") or "").strip()
    ideal_note = (payload.get("ideal_note") or "").strip()
    tags = payload.get("tags", [])

    if not procedure or not shorthand_input or not ideal_note:
        return jsonify({"error": "Procedure, shorthand input, and ideal note are required"}), 400

    tags_str = ", ".join(tags) if isinstance(tags, list) else str(tags)

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO procedure_samples (procedure, title, shorthand_input, ideal_note, tags)
        VALUES (?, ?, ?, ?, ?)
        """,
        (procedure, title, shorthand_input, ideal_note, tags_str)
    )
    conn.commit()
    conn.close()

    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(debug=True, port=5001)