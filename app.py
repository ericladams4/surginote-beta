import hashlib
import json
import os
import re
import secrets
import smtplib
import sqlite3
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from email.message import EmailMessage
from functools import wraps
from pathlib import Path
from time import perf_counter

import requests
from dotenv import load_dotenv
from flask import (
    Flask,
    jsonify,
    render_template,
    request,
    session,
    redirect,
    url_for,
    Response,
    stream_with_context,
)
from openai import OpenAI, RateLimitError
from werkzeug.security import check_password_hash, generate_password_hash

from parser import build_case_facts
from prompt_builder import build_prompt, build_scenario_generation_prompt
from config import PUBLIC_WARNING, PROCEDURE_LABELS
from db import init_db, get_conn
from scenario_catalog import (
    GENERAL_SURGERY_MODULES,
    GENERAL_SURGERY_MODULE_MAP,
    SCENARIO_BLUEPRINTS,
)

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
TRAINING_STATUSES = ("draft", "approved", "gold", "needs_review")
SCENARIO_GRADE_LEVELS = ("needs_revision", "level_1_pass", "level_2_pass", "level_3_pass")
EXPERT_REQUEST_KINDS = ("gold_standard_note", "needed_scenario")
EXPERT_REQUEST_STATUSES = ("pending", "submitted", "completed")
SPECIALTY_OPTIONS = [
    "General Surgery",
    "Trauma / Acute Care Surgery",
    "Colorectal Surgery",
    "Breast Surgery",
    "Hepatobiliary Surgery",
    "Surgical Oncology",
    "Vascular Surgery",
    "Transplant Surgery",
    "Pediatric Surgery",
    "Cardiothoracic Surgery",
    "Urology",
    "Neurosurgery",
    "Orthopedic Surgery",
    "Plastic Surgery",
    "ENT / Head and Neck Surgery",
    "Ophthalmology",
    "Obstetrics and Gynecology",
    "Other",
]
DEFAULT_SPECIALTY = "General Surgery"
ACTIVE_CURRICULUM_SPECIALTY = "General Surgery"
RUNTIME_RETRIEVAL_LIMIT = 3
USER_CREDENTIAL_CHOICES = ("student", "MD", "DO", "NP", "PA")
OUTPUT_FONT_FAMILY_CHOICES = (
    ("system-ui", "System Sans"),
    ("Georgia, serif", "Georgia"),
    ("\"Helvetica Neue\", Helvetica, Arial, sans-serif", "Helvetica"),
    ("Arial, sans-serif", "Arial"),
    ("\"Times New Roman\", Times, serif", "Times"),
    ("ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace", "Monospace"),
)
OUTPUT_FONT_SIZE_CHOICES = ("14px", "15px", "16px", "18px", "20px")
LEGACY_FEEDBACK_SCORE_MAP = {
    "usable_as_is": 10.0,
    "small_edits": 7.0,
    "major_edits": 4.0,
    "wrong_or_unsafe": 1.0,
}
LEGACY_FEEDBACK_LABEL_MAP = {
    "usable_as_is": "10/10",
    "small_edits": "7/10",
    "major_edits": "4/10",
    "wrong_or_unsafe": "1/10",
}
NOTE_TYPE_CHOICES = [
    {"value": "consult_note", "label": "Consult Note", "detail": "Inpatient or ED surgical consults"},
    {"value": "clinic_note", "label": "Clinic Note", "detail": "Office visits and follow-up notes"},
    {"value": "op_note", "label": "Op Note", "detail": "Operative reports and procedures"},
]
DEFAULT_MODEL_NAME = "gpt-5-mini"
DEFAULT_MODEL_TEMPERATURE = 0.0
DEFAULT_MODEL_MAX_OUTPUT_TOKENS = 900
MODEL_CALL_LIMIT_PER_HOUR = 60
DAILY_COST_ALERT_CACHE = set()

init_db()


class GenerationLimitError(Exception):
    pass


def _migrate_feedback_scores():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, rating, feedback_score FROM feedback")
    updates = []
    for row in cur.fetchall():
        rating = (row["rating"] or "").strip()
        current_score = row["feedback_score"]
        migrated_score = None
        if rating in LEGACY_FEEDBACK_SCORE_MAP and (current_score is None or float(current_score or 0) <= 1.01):
            migrated_score = LEGACY_FEEDBACK_SCORE_MAP[rating]
        else:
            parsed_score = _feedback_score(rating)
            if parsed_score and current_score is None:
                migrated_score = parsed_score
        if migrated_score is not None:
            updates.append((migrated_score, row["id"]))
    if updates:
        cur.executemany("UPDATE feedback SET feedback_score = ? WHERE id = ?", updates)
        conn.commit()
    conn.close()


def require_beta_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        return f(*args, **kwargs)
    return decorated


def require_user_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("phone_authed"):
            return redirect(url_for("phone_login"))
        return f(*args, **kwargs)
    return decorated


def require_admin_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get("admin_authed") or session.get("is_admin_user"):
            return f(*args, **kwargs)
        return redirect(url_for("admin_login"))
    return decorated


def require_trainer_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get("trainer_id"):
            return f(*args, **kwargs)
        return redirect(url_for("trainer_login"))
    return decorated


def require_expert_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("beta_authed"):
            return redirect(url_for("login"))
        if not session.get("phone_authed"):
            return redirect(url_for("phone_login"))
        if session.get("is_expert_user"):
            return f(*args, **kwargs)
        return redirect(url_for("index"))
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


def _format_phone_display(phone: str) -> str:
    normalized = normalize_phone(phone or "")
    if not normalized:
        return ""

    digits = re.sub(r"\D", "", normalized)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    return normalized


def _single_line_preview(text: str, limit: int = 150) -> str:
    compact = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(compact) <= limit:
        return compact
    shortened = compact[: limit - 1].rsplit(" ", 1)[0].strip()
    return f"{shortened or compact[: limit - 1]}…"


def _hash_prompt(prompt: str) -> str:
    return hashlib.sha256(str(prompt or "").encode("utf-8")).hexdigest()


def _user_recent_generation_count(user_id, minutes=60):
    if not user_id:
        return 0

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT COUNT(*) AS total
        FROM model_usage
        WHERE user_id = ?
          AND created_at >= datetime('now', ?)
        """,
        (user_id, f"-{int(minutes)} minutes"),
    )
    total = cur.fetchone()["total"] or 0
    conn.close()
    return total


def _case_primary_diagnosis(case_facts):
    case_facts = case_facts or {}
    normalized = str(case_facts.get("normalized_input") or "").lower()
    imaging = case_facts.get("clinical_context", {}).get("imaging") or []

    imaging_map = {
        "ct_appendicitis": "appendicitis",
        "ct_sbo": "small bowel obstruction",
        "ultrasound_gallstones": "cholelithiasis",
        "ct_cholecystitis": "acute cholecystitis",
    }
    for item in imaging:
        if item in imaging_map:
            return imaging_map[item]

    keyword_map = [
        ("appendicitis", "appendicitis"),
        ("appy", "appendicitis"),
        ("small bowel obstruction", "small bowel obstruction"),
        ("sbo", "small bowel obstruction"),
        ("cholecystitis", "acute cholecystitis"),
        ("choledocholithiasis", "choledocholithiasis"),
        ("choledocho", "choledocholithiasis"),
        ("gallstones", "cholelithiasis"),
        ("symptomatic cholelithiasis", "cholelithiasis"),
        ("perforated gastric ulcer", "perforated gastric ulcer"),
        ("gastric ulcer", "gastric ulcer"),
        ("free air", "viscus perforation"),
        ("hernia", "hernia"),
    ]
    for needle, label in keyword_map:
        if needle in normalized:
            return label
    return ""


def _build_asserted_facts(case_facts):
    operative_details = (case_facts or {}).get("operative_details") or {}
    return {
        "procedure": (case_facts or {}).get("procedure") or "",
        "diagnosis": _case_primary_diagnosis(case_facts),
        "laterality": operative_details.get("laterality") or "",
        "estimated_blood_loss": operative_details.get("estimated_blood_loss") or "",
        "specimen": operative_details.get("specimen") or "",
        "implants": operative_details.get("implants") or "",
        "cpt_codes": operative_details.get("cpt_codes") or [],
    }


def _normalize_assertion_value(value):
    if isinstance(value, list):
        return [_normalize_assertion_value(item) for item in value]
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


def _extract_asserted_facts_block(text):
    raw_text = str(text or "")
    match = re.search(
        r"---ASSERTED_FACTS---\s*(\{.*?\})\s*---END_ASSERTED_FACTS---",
        raw_text,
        flags=re.DOTALL,
    )
    asserted = {}
    cleaned = raw_text
    if match:
        block = match.group(1).strip()
        try:
            parsed = json.loads(block)
            if isinstance(parsed, dict):
                asserted = parsed
        except json.JSONDecodeError:
            asserted = {}
        cleaned = (raw_text[:match.start()] + raw_text[match.end():]).strip()
    return cleaned, asserted


def _append_editor_note(existing_notes, note_line):
    existing = str(existing_notes or "").strip()
    note_line = str(note_line or "").strip()
    if not note_line:
        return existing
    if not existing:
        return note_line
    return f"{existing}\n{note_line}"


def _response_usage_dict(response):
    usage = getattr(response, "usage", None)
    if usage is None and hasattr(response, "model_dump"):
        response_dump = response.model_dump()
        usage = response_dump.get("usage") or response_dump.get("meta", {}).get("usage")

    if usage is None:
        return {}
    if isinstance(usage, dict):
        return usage
    if hasattr(usage, "model_dump"):
        return usage.model_dump()

    usage_dict = {}
    for key in ("total_tokens", "input_tokens", "output_tokens", "prompt_tokens", "completion_tokens", "cost_usd"):
        value = getattr(usage, key, None)
        if value is not None:
            usage_dict[key] = value
    return usage_dict


def _response_output_text(response):
    text = getattr(response, "output_text", None)
    if text:
        return text

    def _collect_text_chunks(value):
        chunks = []
        if isinstance(value, (list, tuple)):
            for item in value:
                chunks.extend(_collect_text_chunks(item))
            return chunks
        if isinstance(value, dict):
            if value.get("type") != "message":
                return chunks
            for content in value.get("content", []) or []:
                if content.get("type") == "output_text":
                    piece = content.get("text")
                    if isinstance(piece, str) and piece:
                        chunks.append(piece)
            return chunks

        if getattr(value, "type", None) != "message":
            return chunks
        for content in getattr(value, "content", []) or []:
            if getattr(content, "type", None) == "output_text":
                piece = getattr(content, "text", None)
                if isinstance(piece, str) and piece:
                    chunks.append(piece)
        return chunks

    if hasattr(response, "output") and response.output:
        chunks = _collect_text_chunks(response.output)
        if chunks:
            return "".join(chunks)

    if hasattr(response, "model_dump"):
        response_dump = response.model_dump()
        dump_output_text = response_dump.get("output_text")
        if isinstance(dump_output_text, str) and dump_output_text:
            return dump_output_text
        chunks = _collect_text_chunks(response_dump.get("output", []) or [])
        if chunks:
            return "".join(chunks)

    return ""


def _response_debug_summary(response):
    status = getattr(response, "status", None)
    error = getattr(response, "error", None)
    incomplete_details = getattr(response, "incomplete_details", None)
    output = getattr(response, "output", None) or []

    item_types = []
    for item in output:
        item_type = getattr(item, "type", None)
        if item_type:
            item_types.append(item_type)

    details = []
    if status:
        details.append(f"status={status}")
    if item_types:
        details.append(f"output={','.join(item_types)}")
    if incomplete_details:
        details.append(f"incomplete={incomplete_details}")
    if error:
        details.append(f"error={error}")
    return "; ".join(details)


def _should_retry_empty_output(debug_summary):
    summary = str(debug_summary or "").lower()
    return "max_output_tokens" in summary or ("output=reasoning" in summary and "status=incomplete" in summary)


def _note_generation_output_budget(note_type):
    note_kind = str(note_type or "").strip().lower()
    if note_kind == "op_note":
        return 2200
    if note_kind == "consult_note":
        return 1600
    if note_kind == "clinic_note":
        return 1400
    return DEFAULT_MODEL_MAX_OUTPUT_TOKENS


def daily_cost_alert(threshold_usd=50.0):
    admin_alert_email = os.getenv("ADMIN_ALERT_EMAIL")
    if not admin_alert_email:
        return False

    today_key = datetime.now().strftime("%Y-%m-%d")
    if today_key in DAILY_COST_ALERT_CACHE:
        return False

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT ROUND(COALESCE(SUM(cost_usd), 0), 4) AS total_cost
        FROM model_usage
        WHERE date(created_at, 'localtime') = date('now', 'localtime')
        """
    )
    total_cost = float(cur.fetchone()["total_cost"] or 0.0)
    conn.close()

    if total_cost < float(threshold_usd):
        return False

    subject = f"SurgiNote daily model cost alert: ${total_cost:.2f}"
    body = (
        f"Today's logged model usage has reached ${total_cost:.2f}, "
        f"which is above the alert threshold of ${float(threshold_usd):.2f}."
    )
    sent = _send_email_message(admin_alert_email, subject, body)
    if sent:
        DAILY_COST_ALERT_CACHE.add(today_key)
    return sent


def call_model_and_log(
    prompt,
    user_id=None,
    training_example_id=None,
    model=DEFAULT_MODEL_NAME,
    temperature=DEFAULT_MODEL_TEMPERATURE,
    max_output_tokens=DEFAULT_MODEL_MAX_OUTPUT_TOKENS,
):
    if user_id and _user_recent_generation_count(user_id, minutes=60) >= MODEL_CALL_LIMIT_PER_HOUR:
        raise GenerationLimitError("Hourly generation limit reached. Please try again shortly.")

    request_payload = {
        "model": model,
        "input": prompt,
        "max_output_tokens": max_output_tokens,
    }
    if str(model).startswith("gpt-5"):
        request_payload["reasoning"] = {"effort": "low"}

    response = client.responses.create(**request_payload)
    text_output = (_response_output_text(response) or "").strip()
    debug_summary = _response_debug_summary(response)
    if _should_retry_empty_output(debug_summary):
        retry_payload = dict(request_payload)
        retry_payload["max_output_tokens"] = max(int(max_output_tokens or 0) * 2, int(max_output_tokens or 0) + 1200, 2200)
        response = client.responses.create(**retry_payload)
        text_output = (_response_output_text(response) or "").strip()
        debug_summary = _response_debug_summary(response)
    usage_dict = _response_usage_dict(response)
    tokens_used = usage_dict.get("total_tokens")
    if tokens_used is None:
        input_tokens = usage_dict.get("input_tokens") or usage_dict.get("prompt_tokens") or 0
        output_tokens = usage_dict.get("output_tokens") or usage_dict.get("completion_tokens") or 0
        tokens_used = input_tokens + output_tokens or None
    cost_usd = usage_dict.get("cost_usd")

    try:
        conn = get_conn()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO model_usage (
                    training_example_id, user_id, model, prompt_hash, tokens_used, cost_usd, response_preview
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    training_example_id,
                    user_id,
                    model,
                    _hash_prompt(prompt),
                    tokens_used,
                    cost_usd,
                    _single_line_preview(text_output, limit=240),
                ),
            )
            conn.commit()
        finally:
            conn.close()
    except sqlite3.OperationalError as exc:
        if "database is locked" not in str(exc).lower():
            raise

    try:
        daily_cost_alert()
    except sqlite3.OperationalError as exc:
        if "database is locked" not in str(exc).lower():
            raise
    if not text_output:
        if debug_summary:
            raise ValueError(f"Empty model output ({debug_summary}).")
        raise ValueError("Empty model output.")
    return text_output, usage_dict


def two_stage_generate(
    shorthand,
    user_id=None,
    note_type="op_note",
    template_profile=None,
    training_example_id=None,
    specialty=DEFAULT_SPECIALTY,
    template_content=None,
    retrieved_examples=None,
    case_facts=None,
    global_tone_profile=None,
):
    facts = case_facts or build_case_facts(shorthand)
    primary_diagnosis = _case_primary_diagnosis(facts)
    if not facts.get("procedure") and not primary_diagnosis:
        raise ValueError("Procedure or diagnosis must be identifiable before generation.")

    effective_template = template_content
    if effective_template is None and template_profile and template_profile.get("strict_enabled"):
        effective_template = (template_profile.get("strict_template_text") or "").strip() or None

    prompt = build_prompt(
        case_facts=facts,
        note_type=note_type,
        template_content=effective_template,
        specialty=specialty,
        retrieved_examples=retrieved_examples,
        template_profile=template_profile,
        global_tone_profile=global_tone_profile,
    )
    asserted_facts = _build_asserted_facts(facts)
    prompt = (
        f"{prompt}\n\n---ASSERTED_FACTS---\n"
        f"{json.dumps(asserted_facts, ensure_ascii=True)}\n"
        f"---END_ASSERTED_FACTS---"
    )

    try:
        draft_with_assertions, usage = call_model_and_log(
            prompt,
            user_id=user_id,
            training_example_id=training_example_id,
            model=DEFAULT_MODEL_NAME,
            temperature=0.0,
            max_output_tokens=_note_generation_output_budget(note_type),
        )
        draft_text, asserted_from_model = _extract_asserted_facts_block(draft_with_assertions)
        if not str(draft_text or "").strip():
            raise ValueError("Model response did not include a note draft.")
    except Exception as exc:
        if not _connection_error_message(exc):
            raise
        draft_text = _fallback_note_from_case_facts(note_type, facts)
        asserted_from_model = {}
        usage = {
            "fallback_used": True,
            "fallback_reason": str(exc),
        }

    expected_procedure = _normalize_assertion_value(facts.get("procedure"))
    asserted_procedure = _normalize_assertion_value(asserted_from_model.get("procedure"))
    procedure_match = not expected_procedure or not asserted_procedure or expected_procedure == asserted_procedure

    validation = {
        "procedure_match": procedure_match,
        "expected_procedure": facts.get("procedure") or "",
        "asserted_procedure": asserted_from_model.get("procedure") or "",
        "primary_diagnosis": primary_diagnosis,
    }

    if training_example_id and not procedure_match:
        note_line = (
            f"Procedure assertion mismatch detected at {datetime.now(timezone.utc).isoformat()}: "
            f"expected {facts.get('procedure') or '[missing]'} but model asserted "
            f"{asserted_from_model.get('procedure') or '[missing]'}."
        )
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT editor_notes FROM training_examples WHERE id = ?", (training_example_id,))
        row = cur.fetchone()
        existing_notes = row["editor_notes"] if row else ""
        cur.execute(
            """
            UPDATE training_examples
            SET status = 'needs_review',
                editor_notes = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                _append_editor_note(existing_notes, note_line),
                training_example_id,
            ),
        )
        conn.commit()
        conn.close()

    return draft_text, {
        "usage": usage,
        "asserted_from_model": asserted_from_model,
        "validation": validation,
        "prompt_hash": _hash_prompt(prompt),
        "case_facts": facts,
    }


def _deidentify_phi_text(text: str):
    sanitized = str(text or "").strip()
    replacement_count = 0

    patterns = [
        (r"(?im)\b(patient name|pt name|name)\s*:\s*[^\n]+", lambda m: f"{m.group(1)}: [PATIENT NAME]"),
        (r"(?im)\b(address)\s*:\s*[^\n]+", lambda m: f"{m.group(1)}: [ADDRESS]"),
        (r"(?im)\b(?:dob|date of birth)\s*:\s*[^\n]+", lambda m: "DOB: [DATE]"),
        (r"(?im)\b(?:mrn|medical record number|account|acct|csn|fin)\s*[:#]?\s*[A-Z0-9\-]+\b", "[ID]"),
        (r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", "[EMAIL]"),
        (r"(?:\+?1[\s.\-]?)?(?:\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4})", "[PHONE]"),
        (r"\b\d{3}-\d{2}-\d{4}\b", "[SSN]"),
        (r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2})\b", "[DATE]"),
        (r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s+\d{1,2},?\s+\d{2,4}\b", "[DATE]"),
    ]

    for pattern, replacement in patterns:
        sanitized, count = re.subn(pattern, replacement, sanitized, flags=re.IGNORECASE)
        replacement_count += count

    sanitized = re.sub(r"\n{3,}", "\n\n", sanitized).strip()
    return sanitized, replacement_count


def _canonical_note_title(note_text: str, fallback_note_type: str):
    for line in str(note_text or "").splitlines():
        clean = re.sub(r"\s+", " ", line).strip(" -:\t")
        if len(clean) >= 8:
            return clean[:100]
    return f"Canonical {fallback_note_type.replace('_', ' ').title()}"


def _note_type_label(note_type):
    for choice in NOTE_TYPE_CHOICES:
        if choice["value"] == note_type:
            return choice["label"]
    return "Note"


def _connection_error_message(exc):
    return "connection error" in str(exc or "").strip().lower()


def _join_sentence_parts(parts):
    cleaned = [str(part or "").strip().rstrip(".") for part in parts if str(part or "").strip()]
    if not cleaned:
        return ""
    return ". ".join(cleaned) + "."


def _fallback_consult_note(case_facts):
    facts = case_facts or {}
    diagnosis = _case_primary_diagnosis(facts) or "acute surgical problem"
    demographics = facts.get("demographics") or {}
    clinical = facts.get("clinical_context") or {}
    formal_exam = clinical.get("formal_exam") or {}
    labs = clinical.get("labs") or {}
    symptoms = clinical.get("symptoms") or []
    plans = clinical.get("plan_signals") or []
    pain = clinical.get("pain_characteristics") or {}
    review = clinical.get("review_of_systems") or {}

    patient_parts = []
    if demographics.get("age"):
        patient_parts.append(f"{demographics['age']}-year-old")
    if demographics.get("sex"):
        patient_parts.append(str(demographics["sex"]))
    patient_label = " ".join(patient_parts) or "Adult patient"

    symptom_labels = []
    symptom_map = {
        "abdominal_pain": "abdominal pain",
        "nausea": "nausea",
        "vomiting": "vomiting",
        "anorexia": "decreased appetite",
        "poor_po": "poor oral intake",
        "fever": "fever",
        "chills": "chills",
    }
    for symptom in symptoms:
        label = symptom_map.get(symptom)
        if label and label not in symptom_labels:
            symptom_labels.append(label)

    hpi_parts = [patient_label]
    duration = facts.get("raw_input") or ""
    duration_match = re.search(r"(\d+\s*(?:hours?|hrs?|days?|weeks?))", duration, flags=re.IGNORECASE)
    if duration_match:
        hpi_parts.append(f"with {duration_match.group(1)} of symptoms")
    if symptom_labels:
        hpi_parts.append("including " + ", ".join(symptom_labels))
    if diagnosis:
        hpi_parts.append(f"with imaging and presentation concerning for {diagnosis}")

    objective_lines = []
    if formal_exam.get("gen"):
        objective_lines.append(f"Gen: {formal_exam['gen']}")
    if formal_exam.get("heent"):
        objective_lines.append(f"HEENT: {formal_exam['heent']}")
    if formal_exam.get("pulmonary"):
        objective_lines.append(f"Pulmonary: {formal_exam['pulmonary']}")
    if formal_exam.get("cardiovascular"):
        objective_lines.append(f"Cardiovascular: {formal_exam['cardiovascular']}")
    abdomen_line = formal_exam.get("abdomen")
    if not abdomen_line and pain.get("location"):
        abdomen_line = f"Abdomen soft with {pain.get('location')} tenderness to palpation"
    if abdomen_line:
        objective_lines.append(f"Abdomen: {abdomen_line}")
    if labs.get("wbc"):
        objective_lines.append(f"Labs: WBC {labs['wbc']}")

    imaging_text = "CT imaging supports appendicitis." if "appendicitis" in diagnosis else ""
    if imaging_text:
        objective_lines.append(f"Imaging: {imaging_text}")

    plan_parts = []
    if "admit" in plans:
        plan_parts.append("Admit to the surgical service")
    if "npo" in plans:
        plan_parts.append("Keep NPO")
    if "antibiotics" in plans:
        plan_parts.append("Continue IV antibiotics")
    if "iv_fluids" in plans:
        plan_parts.append("Provide IV fluids")
    if facts.get("procedure") == "laparoscopic_appendectomy" or "appendicitis" in diagnosis:
        plan_parts.append("Plan laparoscopic appendectomy when OR timing allows")
    if not plan_parts:
        plan_parts.append("Continue surgical evaluation and finalize operative versus nonoperative plan")

    ros_positive = []
    for key, value in review.items():
        value_text = str(value or "").strip()
        if value_text.lower().startswith("positive"):
            ros_positive.append(value_text)

    sections = [
        ("Reason for Consult", f"Evaluation and management of {diagnosis}."),
        ("HPI", _join_sentence_parts(hpi_parts)),
        ("Past Medical History", clinical.get("past_medical_history") or "None reported."),
        ("Past Surgical History", clinical.get("past_surgical_history") or "None reported."),
        ("Family History", "Non-contributory."),
        ("Social History", "Not provided in shorthand."),
        ("Review of Systems", _join_sentence_parts(ros_positive) or "Negative except as noted in HPI."),
        ("Objective", "\n".join(objective_lines) if objective_lines else "Focused exam and data reviewed."),
        ("Assessment and Plan", _join_sentence_parts([
            f"{patient_label} with suspected {diagnosis}",
            *plan_parts,
        ])),
    ]

    return "\n\n".join(f"{heading}:\n{body}" for heading, body in sections if body)


def _fallback_note_from_case_facts(note_type, case_facts):
    if note_type == "consult_note":
        return _fallback_consult_note(case_facts)
    diagnosis = _case_primary_diagnosis(case_facts) or "surgical condition"
    return f"{_note_type_label(note_type)}\n\nAssessment:\nConcern for {diagnosis}.\n\nPlan:\nDocument key facts from shorthand and continue surgical management."


def _normalize_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _normalize_credential_title(value):
    raw = (value or "").strip()
    lowered = raw.lower()
    if lowered == "student":
        return "student"
    if raw.upper() in {"MD", "DO", "NP", "PA"}:
        return raw.upper()
    return ""


def _user_full_name(user):
    if not user:
        return ""
    first_name = (user.get("first_name") or "").strip() if isinstance(user, dict) else (user["first_name"] or "").strip() if "first_name" in user.keys() else ""
    last_name = (user.get("last_name") or "").strip() if isinstance(user, dict) else (user["last_name"] or "").strip() if "last_name" in user.keys() else ""
    return " ".join(part for part in [first_name, last_name] if part)


def _user_header_label(user):
    if not user:
        return "Account"
    full_name = _user_full_name(user)
    last_name = (user.get("last_name") or "").strip() if isinstance(user, dict) else (user["last_name"] or "").strip() if "last_name" in user.keys() else ""
    credential_title = (user.get("credential_title") or "").strip() if isinstance(user, dict) else (user["credential_title"] or "").strip() if "credential_title" in user.keys() else ""
    if last_name and credential_title and credential_title.lower() != "student":
        return f"{last_name}, {credential_title}"
    if last_name:
        return last_name
    if full_name:
        return full_name
    return "Account"


def _user_display_with_title(user):
    if not user:
        return ""
    full_name = _user_full_name(user)
    credential_title = (user.get("credential_title") or "").strip() if isinstance(user, dict) else (user["credential_title"] or "").strip() if "credential_title" in user.keys() else ""
    if full_name and credential_title:
        title_display = "Student" if credential_title.lower() == "student" else credential_title
        return f"{full_name}, {title_display}"
    return full_name or "Unknown user"


def _user_profile_complete(user):
    if not user:
        return False
    full_name = _user_full_name(user)
    credential_title = (user.get("credential_title") or "").strip() if isinstance(user, dict) else (user["credential_title"] or "").strip() if "credential_title" in user.keys() else ""
    return bool(full_name and credential_title in USER_CREDENTIAL_CHOICES)


def get_or_create_user(phone: str):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT id, phone, first_name, last_name, credential_title,
               COALESCE(is_admin, 0) AS is_admin, COALESCE(is_expert, 0) AS is_expert
        FROM users
        WHERE phone = ?
        """,
        (phone,),
    )
    user = cur.fetchone()

    if not user:
        cur.execute("INSERT INTO users (phone) VALUES (?)", (phone,))
        conn.commit()
        cur.execute(
            """
            SELECT id, phone, first_name, last_name, credential_title,
                   COALESCE(is_admin, 0) AS is_admin, COALESCE(is_expert, 0) AS is_expert
            FROM users
            WHERE phone = ?
            """,
            (phone,),
        )
        user = cur.fetchone()

    conn.close()
    return user


def _log_user_login(user_id):
    if not user_id:
        return
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE users
            SET login_count = COALESCE(login_count, 0) + 1,
                last_login_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (user_id,),
        )
        conn.commit()
    finally:
        conn.close()


def _log_generated_note(user_id, note_type, shorthand, generated_note, procedure_label=""):
    if not generated_note:
        return
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO generated_notes (
                user_id, note_type, shorthand, generated_note, procedure_label
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                user_id,
                note_type,
                shorthand,
                generated_note,
                procedure_label or None,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _sync_admin_session_from_user(user):
    if not user:
        is_admin_user = False
        is_expert_user = False
        user_id = None
    else:
        is_admin_user = bool(user["is_admin"]) if "is_admin" in user.keys() else False
        is_expert_user = bool(user["is_expert"]) if "is_expert" in user.keys() else False
        user_id = user["id"] if "id" in user.keys() else None
    session["is_admin_user"] = is_admin_user
    session["is_expert_user"] = is_expert_user
    session["user_header_label"] = _user_header_label(user if isinstance(user, dict) else dict(user))
    session["user_display_name"] = _user_display_with_title(user if isinstance(user, dict) else dict(user))
    if is_admin_user:
        session["admin_authed"] = True
        session["admin_id"] = user_id
    else:
        session.pop("admin_id", None)


def _admin_user_rows():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, phone, email, COALESCE(is_admin, 0) AS is_admin, created_at
        FROM users
        WHERE COALESCE(is_admin, 0) = 1
        ORDER BY created_at DESC, id DESC
        """
    )
    rows = [dict(row) for row in cur.fetchall()]
    conn.close()
    return rows


def _role_user_rows():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, phone, email, first_name, last_name, credential_title,
               COALESCE(is_admin, 0) AS is_admin, COALESCE(is_expert, 0) AS is_expert, created_at
        FROM users
        WHERE COALESCE(is_admin, 0) = 1 OR COALESCE(is_expert, 0) = 1
        ORDER BY created_at DESC, id DESC
        """
    )
    rows = [dict(row) for row in cur.fetchall()]
    conn.close()
    for row in rows:
        row["display_name"] = _user_display_with_title(row)
        row["header_label"] = _user_header_label(row)
    return rows


def _expert_user_rows():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT u.id, u.phone, u.email, u.first_name, u.last_name, u.credential_title, u.created_at,
               COALESCE(SUM(CASE WHEN er.status = 'pending' THEN 1 ELSE 0 END), 0) AS pending_request_count,
               COALESCE(SUM(CASE WHEN er.status = 'submitted' THEN 1 ELSE 0 END), 0) AS submitted_request_count,
               COALESCE(SUM(CASE WHEN er.status = 'completed' THEN 1 ELSE 0 END), 0) AS completed_request_count
        FROM users u
        LEFT JOIN expert_requests er ON er.expert_user_id = u.id
        WHERE COALESCE(u.is_expert, 0) = 1
        GROUP BY u.id, u.phone, u.email, u.created_at
        ORDER BY pending_request_count DESC, u.created_at DESC, u.id DESC
        """
    )
    rows = [dict(row) for row in cur.fetchall()]
    conn.close()
    for row in rows:
        row["display_name"] = _user_display_with_title(row)
        row["phone_display"] = _format_phone_display(row.get("phone"))
    return rows


def _current_user_row():
    user_id = session.get("user_id")
    if not user_id:
        return None
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, phone, email, first_name, last_name, credential_title,
               COALESCE(is_admin, 0) AS is_admin, COALESCE(is_expert, 0) AS is_expert
        FROM users
        WHERE id = ?
        """,
        (user_id,),
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    data = dict(row)
    data["display_name"] = _user_display_with_title(data)
    data["header_label"] = _user_header_label(data)
    return data


def _pending_expert_request_count(user_id):
    if not user_id:
        return 0
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) AS total FROM expert_requests WHERE expert_user_id = ? AND status = 'pending'",
        (user_id,),
    )
    count = cur.fetchone()["total"] or 0
    conn.close()
    return count


def _scenario_batch_date():
    return datetime.now().strftime("%Y-%m-%d")


def _daily_urgent_scenarios(cur, batch_date=None, limit=5):
    target_batch_date = batch_date or _scenario_batch_date()
    cur.execute(
        """
        SELECT id, specialty, note_type, title, module_key, module_label, module_rank, diagnosis, procedure_focus,
               complexity_level, scenario_status, scenario_brief, learning_objectives, model_confidence, review_count,
               approved_count, gold_count, average_edit_similarity, next_target_level, user_feedback_score,
               user_feedback_count, curriculum_pressure, updated_at, batch_date, urgency_rank, question_prompt, why_now
        FROM scenario_templates
        WHERE specialty = ?
          AND generated_by = 'daily-urgent-scenario-generator'
          AND batch_date = ?
        ORDER BY COALESCE(urgency_rank, 999) ASC, curriculum_pressure DESC, updated_at DESC
        LIMIT ?
        """,
        (ACTIVE_CURRICULUM_SPECIALTY, target_batch_date, limit),
    )
    return [_prepare_scenario_for_display(row) for row in cur.fetchall()]


def _top_urgent_scenarios(cur, limit=5):
    cur.execute(
        """
        SELECT id, specialty, note_type, title, module_key, module_label, module_rank, diagnosis, procedure_focus,
               complexity_level, scenario_status, scenario_brief, learning_objectives, model_confidence, review_count,
               approved_count, gold_count, average_edit_similarity, next_target_level, user_feedback_score,
               user_feedback_count, curriculum_pressure, updated_at, batch_date, urgency_rank, question_prompt, why_now
        FROM scenario_templates
        WHERE specialty = ?
        ORDER BY curriculum_pressure DESC, COALESCE(user_feedback_score, 0) ASC, model_confidence ASC,
                 next_target_level ASC, COALESCE(module_rank, 999) ASC, updated_at DESC
        LIMIT ?
        """,
        (ACTIVE_CURRICULUM_SPECIALTY, limit),
    )
    return [_prepare_scenario_for_display(row) for row in cur.fetchall()]


def _create_training_example_from_expert_request(cur, request_row, expert_user, submitted_payload):
    note_type = (submitted_payload.get("note_type") or request_row["note_type"] or "consult_note").strip()
    if note_type not in ALLOWED_NOTE_TYPES:
        note_type = "consult_note"

    title = (submitted_payload.get("title") or request_row["title"] or "").strip()
    shorthand_input = (submitted_payload.get("shorthand_input") or "").strip()
    generated_draft = (submitted_payload.get("generated_draft") or "").strip()
    corrected_output = (submitted_payload.get("corrected_output") or "").strip()
    expert_notes = (submitted_payload.get("expert_notes") or "").strip()
    accepted_assumptions_json = (submitted_payload.get("accepted_assumptions_json") or "[]").strip() or "[]"
    request_kind = request_row["request_kind"]
    source_kind = "expert_request_scenario" if request_kind == "needed_scenario" else "expert_request_gold"
    created_by = expert_user.get("phone") or expert_user.get("email") or f"user-{expert_user.get('id')}"

    cur.execute(
        """
        INSERT INTO training_examples (
            specialty, note_type, title, shorthand_input, generated_draft, corrected_output,
            status, issue_tags, editor_notes, created_by, scenario_template_id, source_kind,
            module_key, module_label, accepted_assumptions_json
        )
        VALUES (?, ?, ?, ?, ?, ?, 'needs_review', ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ACTIVE_CURRICULUM_SPECIALTY,
            note_type,
            title or None,
            shorthand_input,
            generated_draft or None,
            corrected_output,
            "expert-request" if request_kind == "needed_scenario" else "gold-standard-request",
            expert_notes or request_row["request_brief"],
            created_by,
            request_row["scenario_template_id"],
            source_kind,
            request_row["module_key"],
            request_row["module_label"],
            accepted_assumptions_json,
        ),
    )
    return cur.lastrowid


def _urgent_scenario_generation_targets(cur, limit=5):
    cur.execute(
        """
        SELECT module_key, module_label, note_type,
               ROUND(AVG(COALESCE(feedback_score, 0)), 4) AS average_score,
               COUNT(*) AS feedback_count
        FROM feedback
        WHERE module_key IS NOT NULL AND module_key != ''
        GROUP BY module_key, module_label, note_type
        ORDER BY average_score ASC, feedback_count DESC, MAX(created_at) DESC
        """
    )
    ranked_modules = []
    seen_modules = set()
    for row in cur.fetchall():
        module_key = _normalize_module_key(row["module_key"])
        if not module_key or module_key in seen_modules:
            continue
        module = GENERAL_SURGERY_MODULE_MAP.get(module_key)
        if not module:
            continue
        avg_score = row["average_score"] if row["average_score"] is not None else 10
        if avg_score <= 4:
            target_level = 1
        elif avg_score <= 7:
            target_level = 2
        else:
            target_level = 3
        feedback_count = row["feedback_count"] or 0
        confidence_gap = max(0.0, 10.0 - avg_score)
        ranked_modules.append({
            "module_key": module_key,
            "module_label": module["label"],
            "note_type": module["note_type"],
            "target_level": target_level,
            "focus": f"Prioritize the documentation failure patterns hurting live scores in {module['label']}. Ask for the exact shorthand, case facts, and final note structure the model still keeps missing.",
            "why_now": f"{module['label']} is averaging {avg_score:.1f}/10 across {feedback_count} rated notes, leaving a {confidence_gap:.1f}-point documentation gap to close.",
            "feedback_count": feedback_count,
            "average_score": avg_score,
        })
        seen_modules.add(module_key)
        if len(ranked_modules) >= limit:
            return ranked_modules

    for module in _curriculum_modules():
        if module["key"] in seen_modules:
            continue
        ranked_modules.append({
            "module_key": module["key"],
            "module_label": module["label"],
            "note_type": module["note_type"],
            "target_level": 2,
            "focus": f"Generate a high-yield case that would improve confidence in {module['label']}. Ask for the specific shorthand and note style details the system should learn next.",
            "why_now": f"{module['label']} still needs more directed examples so the model can stabilize its output style in that domain.",
            "feedback_count": 0,
            "average_score": None,
        })
        if len(ranked_modules) >= limit:
            break
    return ranked_modules


def _ensure_legacy_template_profiles(user_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) AS total FROM template_profiles WHERE user_id = ?",
        (user_id,)
    )
    existing_profile_count = cur.fetchone()["total"] or 0
    if existing_profile_count:
        conn.close()
        return

    cur.execute(
        """
        SELECT note_type, content, created_at, updated_at
        FROM templates
        WHERE user_id = ?
        ORDER BY updated_at DESC, created_at DESC
        """,
        (user_id,)
    )
    legacy_rows = cur.fetchall()

    for row in legacy_rows:
        cur.execute(
            """
            INSERT INTO template_profiles (
                user_id, note_type, name, strict_template_text, strict_enabled,
                style_example_text, style_enabled, is_default, created_at, updated_at,
                strict_template_html, style_example_html, output_font_family, output_font_size
            )
            VALUES (?, ?, ?, ?, 1, '', 0, 1, COALESCE(?, CURRENT_TIMESTAMP), COALESCE(?, CURRENT_TIMESTAMP), ?, '', 'system-ui', '16px')
            """,
            (
                user_id,
                row["note_type"],
                f"{_note_type_label(row['note_type'])} Default",
                row["content"],
                row["created_at"],
                row["updated_at"],
                row["content"],
            )
        )

    conn.commit()
    conn.close()


def _fetch_template_profiles(user_id, note_type=None):
    _ensure_legacy_template_profiles(user_id)
    conn = get_conn()
    cur = conn.cursor()
    query = """
        SELECT id, user_id, note_type, name, strict_template_text, strict_enabled,
               style_example_text, style_enabled, is_default, created_at, updated_at,
               strict_template_html, style_example_html, output_font_family, output_font_size
        FROM template_profiles
        WHERE user_id = ?
    """
    params = [user_id]
    if note_type:
        query += " AND note_type = ?"
        params.append(note_type)
    query += " ORDER BY note_type ASC, is_default DESC, updated_at DESC, created_at DESC"
    cur.execute(query, params)
    rows = [dict(row) for row in cur.fetchall()]
    conn.close()
    return rows


def _fetch_template_profile_by_id(user_id, profile_id):
    _ensure_legacy_template_profiles(user_id)
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, user_id, note_type, name, strict_template_text, strict_enabled,
               style_example_text, style_enabled, is_default, created_at, updated_at,
               strict_template_html, style_example_html, output_font_family, output_font_size
        FROM template_profiles
        WHERE user_id = ? AND id = ?
        """,
        (user_id, profile_id)
    )
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def _fetch_active_template_profile(user_id, note_type):
    profiles = _fetch_template_profiles(user_id, note_type=note_type)
    if not profiles:
        return None
    default_profile = next((profile for profile in profiles if profile["is_default"]), None)
    return default_profile or profiles[0]


def _template_profile_runtime_summary(profile):
    if not profile:
        return None

    strict_text = (profile.get("strict_template_text") or "").strip()
    exact_blocks = re.findall(r"\[\[EXACT\]\](.*?)\[\[/EXACT\]\]", strict_text, flags=re.IGNORECASE | re.DOTALL)
    guide_blocks = re.findall(r"\[\[GUIDE\]\](.*?)\[\[/GUIDE\]\]", strict_text, flags=re.IGNORECASE | re.DOTALL)
    placeholders = re.findall(r"\{([a-zA-Z0-9_]+)\}", strict_text)

    return {
        "id": profile.get("id"),
        "name": profile.get("name"),
        "note_type": profile.get("note_type"),
        "strict_enabled": bool(profile.get("strict_enabled")) and bool(strict_text),
        "exact_block_count": len([block for block in exact_blocks if str(block).strip()]),
        "guide_block_count": len([block for block in guide_blocks if str(block).strip()]),
        "placeholder_count": len(placeholders),
        "exact_blocks": [block.strip() for block in exact_blocks if str(block).strip()],
        "output_font_family": (profile.get("output_font_family") or "system-ui").strip() or "system-ui",
        "output_font_size": (profile.get("output_font_size") or "16px").strip() or "16px",
    }


def _decorate_runtime_summary_with_global_tone(summary, global_tone_profile):
    if not summary:
        return None
    decorated = dict(summary)
    decorated["global_tone_enabled"] = bool((global_tone_profile or {}).get("tone_summary"))
    return decorated


def _get_user_preference(user_id, key, default=None):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT preference_value
        FROM user_preferences
        WHERE user_id = ? AND preference_key = ?
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """,
        (user_id, key),
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        return default
    return row["preference_value"] if row["preference_value"] is not None else default


def _set_user_preference(user_id, key, value):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id
        FROM user_preferences
        WHERE user_id = ? AND preference_key = ?
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """,
        (user_id, key),
    )
    existing = cur.fetchone()
    if existing:
        cur.execute(
            """
            UPDATE user_preferences
            SET preference_value = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (value, existing["id"]),
        )
    else:
        cur.execute(
            """
            INSERT INTO user_preferences (user_id, preference_key, preference_value)
            VALUES (?, ?, ?)
            """,
            (user_id, key, value),
        )
    conn.commit()
    conn.close()


def _delete_user_preference(user_id, key):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM user_preferences WHERE user_id = ? AND preference_key = ?",
        (user_id, key),
    )
    conn.commit()
    conn.close()


def _get_global_tone_profile(user_id):
    raw = _get_user_preference(user_id, "global_tone_profile")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def _build_tone_summary_from_notes(notes_text):
    prompt = f"""
You are helping summarize a surgeon's charting voice from several de-identified example notes.

Read the examples and produce valid JSON only with exactly these keys:
- tone_summary
- tone_traits

Rules:
- tone_summary should be a short paragraph in plain English describing the surgeon's overall documentation voice.
- tone_traits should be an array of 4 to 6 short bullets.
- focus on sentence rhythm, structure, level of detail, surgical tone, preferred terseness vs explanation, and documentation habits.
- do not mention patients, PHI, or that these were examples.
- keep it useful for conditioning future note generation.

EXAMPLE NOTES:
{notes_text}
"""
    response_text, _ = call_model_and_log(
        prompt,
        user_id=None,
        model=DEFAULT_MODEL_NAME,
        temperature=0.0,
        max_output_tokens=700,
    )
    parsed = json.loads(response_text)
    return {
        "tone_summary": str(parsed.get("tone_summary") or "").strip(),
        "tone_traits": [str(item).strip() for item in (parsed.get("tone_traits") or []) if str(item).strip()],
    }


def _normalize_specialty(value):
    specialty = (value or "").strip()
    return specialty or DEFAULT_SPECIALTY


def _curriculum_modules():
    return GENERAL_SURGERY_MODULES


def _normalize_module_key(value):
    module_key = (value or "").strip()
    return module_key if module_key in GENERAL_SURGERY_MODULE_MAP else ""


def _utcnow():
    return datetime.now(timezone.utc)


def _parse_timestamp(value):
    if not value:
        return None
    try:
        cleaned = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _infer_feedback_module(note_type, shorthand, generated_note="", procedure=""):
    haystack = " ".join([
        str(note_type or ""),
        str(shorthand or ""),
        str(generated_note or ""),
        str(procedure or ""),
    ]).lower()

    if note_type == "op_note":
        if any(token in haystack for token in ["appendic", "appendix", "appy"]):
            return "appendectomy_op_note"
        if any(token in haystack for token in ["chole", "gallbladder", "biliary", "cholecyst"]):
            return "cholecystectomy_op_note"

    if note_type == "clinic_note":
        if any(token in haystack for token in ["post-op", "post op", "postoperative", "follow-up", "follow up", "pathology"]):
            return "postop_followup_clinic"
        if any(token in haystack for token in ["hernia", "groin bulge", "inguinal"]):
            return "elective_hernia_clinic"
        if any(token in haystack for token in ["biliary", "gallstone", "gallbladder", "fatty meal", "cholelithiasis"]):
            return "elective_biliary_clinic"

    if note_type == "consult_note":
        if any(token in haystack for token in ["appendic", "appendix", "appy"]):
            return "appendicitis_consult"
        if any(token in haystack for token in ["cholecyst", "gallstone", "gallbladder", "biliary colic", "ruq"]):
            return "cholecystitis_consult"
        if any(token in haystack for token in ["small bowel obstruction", "transition point", "ng tube", "sbo"]):
            return "small_bowel_obstruction_consult"
        if any(token in haystack for token in ["diverticul", "llq pain", "pericolic abscess"]):
            return "diverticulitis_consult"
        if any(token in haystack for token in ["hernia", "incarcerated", "umbilical bulge", "inguinal bulge"]):
            return "hernia_consult"

    return ""


def _module_label(module_key):
    module = GENERAL_SURGERY_MODULE_MAP.get(module_key or "")
    return module["label"] if module else None


def _feedback_score(rating):
    token = str(rating or "").strip()
    if token in LEGACY_FEEDBACK_SCORE_MAP:
        return LEGACY_FEEDBACK_SCORE_MAP[token]
    try:
        numeric = int(token)
    except (TypeError, ValueError):
        return 0.0
    return float(numeric) if 1 <= numeric <= 10 else 0.0


def _feedback_label(rating):
    token = str(rating or "").strip()
    if token in LEGACY_FEEDBACK_LABEL_MAP:
        return LEGACY_FEEDBACK_LABEL_MAP[token]
    try:
        numeric = int(token)
    except (TypeError, ValueError):
        return "Unrated"
    return f"{numeric}/10" if 1 <= numeric <= 10 else "Unrated"


def _format_score(score, decimals=1, suffix="/10", fallback="--"):
    if score is None:
        return fallback
    try:
        numeric = float(score)
    except (TypeError, ValueError):
        return fallback
    if decimals <= 0 or numeric.is_integer():
        return f"{int(round(numeric))}{suffix}"
    return f"{numeric:.{decimals}f}{suffix}"


_migrate_feedback_scores()


def _source_kind_label(source_kind):
    mapping = {
        "manual": "Manual curation",
        "admin-review": "Admin review",
        "scenario_review": "Scenario review",
        "trainer_review": "Trainer submissions",
        "canonical_note": "Master note canon",
        "expert_request_gold": "Expert curated example",
        "expert_request_scenario": "Expert scenario response",
    }
    return mapping.get((source_kind or "").strip(), "Other")


def _build_svg_line_path(values, width=640, height=200, padding=18, value_min=0, value_max=10):
    numeric = [float(v or 0) for v in values]
    if not numeric:
        return ""
    value_span = max(value_max - value_min, 1)
    if len(numeric) == 1:
        x = width / 2
        normalized = min(max((numeric[0] - value_min) / value_span, 0), 1)
        y = height - padding - (normalized * (height - padding * 2))
        return f"M {x:.2f} {y:.2f}"
    usable_width = max(width - padding * 2, 1)
    usable_height = max(height - padding * 2, 1)
    points = []
    for idx, value in enumerate(numeric):
        x = padding + (usable_width * idx / (len(numeric) - 1))
        normalized = min(max((value - value_min) / value_span, 0), 1)
        y = height - padding - (normalized * usable_height)
        points.append(f"{x:.2f},{y:.2f}")
    return "M " + " L ".join(points)


def _build_svg_area_path(values, width=640, height=200, padding=18, value_min=0, value_max=10):
    numeric = [float(v or 0) for v in values]
    if not numeric:
        return ""
    value_span = max(value_max - value_min, 1)
    if len(numeric) == 1:
        x = width / 2
        normalized = min(max((numeric[0] - value_min) / value_span, 0), 1)
        y = height - padding - (normalized * (height - padding * 2))
        baseline = height - padding
        return f"M {x:.2f} {baseline:.2f} L {x:.2f} {y:.2f} L {x:.2f} {baseline:.2f} Z"
    usable_width = max(width - padding * 2, 1)
    usable_height = max(height - padding * 2, 1)
    coords = []
    for idx, value in enumerate(numeric):
        x = padding + (usable_width * idx / (len(numeric) - 1))
        normalized = min(max((value - value_min) / value_span, 0), 1)
        y = height - padding - (normalized * usable_height)
        coords.append((x, y))
    baseline = height - padding
    path = [f"M {coords[0][0]:.2f} {baseline:.2f}"]
    path.extend(f"L {x:.2f} {y:.2f}" for x, y in coords)
    path.append(f"L {coords[-1][0]:.2f} {baseline:.2f}")
    path.append("Z")
    return " ".join(path)


def _build_admin_rating_trend(cur, days=14):
    cur.execute(
        f"""
        WITH RECURSIVE dates(day) AS (
          SELECT date('now', '-{days - 1} days')
          UNION ALL
          SELECT date(day, '+1 day') FROM dates WHERE day < date('now')
        )
        SELECT dates.day AS day,
               COUNT(f.id) AS note_count,
               ROUND(AVG(COALESCE(f.feedback_score, 0)), 4) AS average_score
        FROM dates
        LEFT JOIN feedback f ON date(f.created_at) = dates.day
        GROUP BY dates.day
        ORDER BY dates.day ASC
        """
    )
    rows = cur.fetchall()
    points = []
    for row in rows:
        avg_score = row["average_score"] if row["average_score"] is not None else 0
        points.append({
            "day": row["day"],
            "day_label": datetime.strptime(row["day"], "%Y-%m-%d").strftime("%b %d"),
            "note_count": row["note_count"] or 0,
            "average_score": avg_score,
            "average_score_display": _format_score(avg_score),
        })
    values = [point["average_score"] for point in points]
    latest_scored_point = next((point for point in reversed(points) if (point["note_count"] or 0) > 0), None)
    return {
        "points": points,
        "line_path": _build_svg_line_path(values),
        "area_path": _build_svg_area_path(values),
        "latest_score": latest_scored_point["average_score"] if latest_scored_point else 0,
        "latest_score_display": _format_score(latest_scored_point["average_score"] if latest_scored_point else 0),
    }


def _fetch_admin_recent_generated_notes(cur, limit=50):
    cur.execute(
        """
        SELECT gn.id, gn.note_type, gn.shorthand, gn.generated_note, gn.procedure_label, gn.created_at,
               u.id AS user_id, u.phone, u.email, u.first_name, u.last_name, u.credential_title
        FROM generated_notes gn
        LEFT JOIN users u ON u.id = gn.user_id
        ORDER BY gn.created_at DESC, gn.id DESC
        LIMIT ?
        """,
        (limit,),
    )
    rows = []
    for row in cur.fetchall():
        item = dict(row)
        item["user_display_name"] = _user_display_with_title(item)
        item["user_phone_display"] = _format_phone_display(item.get("phone"))
        item["note_type_label"] = _note_type_label(item.get("note_type"))
        item["shorthand_preview"] = _single_line_preview(item.get("shorthand"), limit=160)
        item["generated_preview"] = _single_line_preview(item.get("generated_note"), limit=220)
        rows.append(item)
    return rows


def _fetch_admin_user_overview(cur, limit=250):
    cur.execute(
        """
        SELECT u.id, u.phone, u.email, u.first_name, u.last_name, u.credential_title,
               u.created_at, u.last_login_at, COALESCE(u.login_count, 0) AS login_count,
               COUNT(DISTINCT gn.id) AS generated_note_count,
               COUNT(DISTINCT f.id) AS rated_note_count,
               COALESCE(u.is_admin, 0) AS is_admin,
               COALESCE(u.is_expert, 0) AS is_expert
        FROM users u
        LEFT JOIN generated_notes gn ON gn.user_id = u.id
        LEFT JOIN feedback f ON f.user_id = u.id
        GROUP BY u.id, u.phone, u.email, u.first_name, u.last_name, u.credential_title,
                 u.created_at, u.last_login_at, u.login_count, u.is_admin, u.is_expert
        ORDER BY u.created_at DESC, u.id DESC
        LIMIT ?
        """,
        (limit,),
    )
    rows = []
    for row in cur.fetchall():
        item = dict(row)
        item["display_name"] = _user_display_with_title(item)
        item["phone_display"] = _format_phone_display(item.get("phone"))
        roles = []
        if item.get("is_admin"):
            roles.append("Admin")
        if item.get("is_expert"):
            roles.append("Expert")
        item["role_label"] = ", ".join(roles) if roles else "User"
        rows.append(item)
    return rows


def _build_admin_teaching_avenues(cur):
    avenue_specs = [
        ("strict_templates", "STRICT templates", "Exact formatting + reusable wording", "strict_used = 1"),
        ("style_examples", "Style examples", "Voice, tone, and organization learning", "style_used = 1"),
        ("exact_phrases", "Exact phrases", "Verbatim must-copy wording blocks", "exact_used_count > 0"),
        ("retrieval_corpus", "Reviewed corpus retrieval", "Gold and approved examples retrieved at generation time", "retrieved_example_count > 0"),
    ]
    avenues = []
    max_count = 1
    for key, label, helper, where_clause in avenue_specs:
        cur.execute(
            f"""
            SELECT COUNT(*) AS usage_count,
                   ROUND(AVG(feedback_score), 4) AS average_score
            FROM feedback
            WHERE {where_clause}
            """
        )
        row = cur.fetchone()
        usage_count = row["usage_count"] or 0
        average_score = row["average_score"] if row["average_score"] is not None else None
        max_count = max(max_count, usage_count)
        avenues.append({
            "key": key,
            "label": label,
            "helper": helper,
            "usage_count": usage_count,
            "average_score": average_score,
            "average_score_display": _format_score(average_score) if average_score is not None else None,
        })

    for avenue in avenues:
        avenue["usage_width"] = round((avenue["usage_count"] / max_count) * 100) if max_count else 0
    avenues.sort(key=lambda row: ((row["average_score"] if row["average_score"] is not None else -1), row["usage_count"]), reverse=True)
    return avenues


def _build_admin_training_guide(cur):
    cur.execute("SELECT COUNT(*) AS total FROM scenario_templates WHERE specialty = ?", (ACTIVE_CURRICULUM_SPECIALTY,))
    scenario_total = cur.fetchone()["total"] or 0
    cur.execute("SELECT COUNT(*) AS total FROM users WHERE COALESCE(is_expert, 0) = 1")
    active_experts = cur.fetchone()["total"] or 0
    cur.execute("SELECT COUNT(*) AS total FROM expert_requests WHERE status = 'pending'")
    pending_submissions = cur.fetchone()["total"] or 0
    cur.execute(
        """
        SELECT source_kind, COUNT(*) AS total
        FROM training_examples
        WHERE status IN ('approved', 'gold')
        GROUP BY source_kind
        """
    )
    source_counts = {row["source_kind"]: row["total"] for row in cur.fetchall()}
    approved_examples = sum(source_counts.values())
    rescue_examples = source_counts.get("admin-review", 0) + source_counts.get("manual", 0)
    cur.execute("SELECT COUNT(*) AS total FROM training_examples WHERE COALESCE(in_master_canon, 0) = 1")
    canonical_examples = cur.fetchone()["total"] or 0
    expert_examples = canonical_examples + source_counts.get("expert_request_gold", 0) + source_counts.get("trainer_review", 0) + source_counts.get("scenario_review", 0)

    return [
        {
            "title": "Low-rated note rescue",
            "helper": "Take real failed deliveries, correct them in-house, and push the weakest live notes back into the global training set.",
            "meta": f"{rescue_examples} rescued examples",
            "eyebrow": "Path 1",
            "links": [
                {
                    "label": "Review live notes",
                    "href": "/admin/trainer?path=1&view=live_notes",
                    "meta": "Find weak outputs from production",
                    "view": "live_notes",
                },
            ],
        },
        {
            "title": "Expert curated examples",
            "helper": "Master note canon entries anchor the system’s best output style, consistency, and retrieval quality.",
            "meta": f"{expert_examples} expert-reviewed examples",
            "eyebrow": "Path 2",
            "links": [
                {
                    "label": "Master note canon",
                    "href": "/admin/trainer?path=2&view=training_library",
                    "meta": f"{canonical_examples} canon notes influencing the model",
                    "view": "training_library",
                    "destination_href": "/admin/training-library",
                },
                {
                    "label": "Gold-standard examples",
                    "href": "/admin/trainer?path=2&view=sample_library",
                    "meta": "Reference examples and canonical teaching assets",
                    "view": "sample_library",
                    "destination_href": "/admin/sample-library",
                },
                {
                    "label": "Submission queue",
                    "href": "/admin/trainer?path=2&view=submission_queue",
                    "meta": f"{pending_submissions} pending expert reviews",
                    "view": "submission_queue",
                    "destination_href": "/admin/trainer-submissions",
                },
            ],
        },
        {
            "title": "Model-generated scenario learning",
            "helper": "Every day the model should surface the five highest-value questions it still needs answered, then learn from the corrected responses.",
            "meta": f"{scenario_total} model-generated scenarios in rotation",
            "eyebrow": "Path 3",
            "links": [
                {
                    "label": "Daily urgent 5",
                    "href": "/admin/trainer?path=3&view=urgent_scenarios",
                    "meta": "Five new model-directed questions each day",
                    "view": "urgent_scenarios",
                    "destination_href": "/admin/trainer?path=3&view=urgent_scenarios",
                },
                {
                    "label": "Expert roster",
                    "href": "/admin/trainer?path=3&view=trainer_roster",
                    "meta": f"{active_experts} SurgiNote Experts available for assignment",
                    "view": "trainer_roster",
                    "destination_href": "/admin/trainer?path=3&view=trainer_roster",
                },
            ],
        },
    ]


def _build_admin_learning_contributions(cur):
    cur.execute("SELECT COUNT(*) AS total FROM scenario_templates WHERE specialty = ?", (ACTIVE_CURRICULUM_SPECIALTY,))
    scenario_total = cur.fetchone()["total"] or 0

    cur.execute("SELECT COUNT(*) AS total FROM procedure_samples")
    sample_total = cur.fetchone()["total"] or 0

    cur.execute(
        """
        SELECT source_kind, COUNT(*) AS total
        FROM training_examples
        WHERE status IN ('approved', 'gold')
        GROUP BY source_kind
        """
    )
    source_counts = {row["source_kind"]: row["total"] for row in cur.fetchall()}

    cur.execute("SELECT COUNT(*) AS total FROM training_examples WHERE COALESCE(in_master_canon, 0) = 1")
    master_canon_total = cur.fetchone()["total"] or 0
    rescue_examples = source_counts.get("admin-review", 0) + source_counts.get("manual", 0)
    expert_gold_examples = source_counts.get("expert_request_gold", 0)
    scenario_examples = (
        source_counts.get("trainer_review", 0)
        + source_counts.get("scenario_review", 0)
        + source_counts.get("expert_request_scenario", 0)
    )

    domains = [
        {
            "eyebrow": "Path 1",
            "title": "Low-rated note rescue",
            "helper": "Rescued live failures pushed back into the learning set.",
            "asset_count": rescue_examples,
            "asset_label": f"{rescue_examples} rescued examples",
        },
        {
            "eyebrow": "Path 2",
            "title": "Expert curated examples",
            "helper": "Master note canon entries and gold-standard references guiding consistent output quality.",
            "asset_count": expert_gold_examples + sample_total + master_canon_total,
            "asset_label": f"{expert_gold_examples + sample_total + master_canon_total} curated assets",
        },
        {
            "eyebrow": "Path 3",
            "title": "Model-generated scenarios",
            "helper": "Scenario queue plus scenario-derived teaching examples in rotation.",
            "asset_count": scenario_total + scenario_examples,
            "asset_label": f"{scenario_total + scenario_examples} scenario inputs",
        },
    ]

    total_assets = sum(domain["asset_count"] for domain in domains)
    if total_assets <= 0:
        total_assets = 0

    for domain in domains:
        share_percent = round((domain["asset_count"] / total_assets) * 100) if total_assets else 0
        domain["share_percent"] = share_percent
        domain["share_display"] = f"{share_percent}%"

    dominant_domain = max(domains, key=lambda row: row["asset_count"], default=None)
    return {
        "domains": domains,
        "total_assets": total_assets,
        "total_assets_display": f"{total_assets} active learning inputs",
        "dominant_title": dominant_domain["title"] if dominant_domain else "No domain data yet",
        "dominant_share_display": dominant_domain["share_display"] if dominant_domain else "0%",
    }


def _fetch_admin_recent_feedback(cur, low_only=False, search="", note_type=""):
    query = """
        SELECT f.id, f.shorthand, f.procedure, f.rating, f.comment, f.generated_note, f.note_type,
               f.delivery_action, f.module_key, f.module_label, f.feedback_score, f.created_at,
               f.template_profile_name, f.strict_used, f.style_used, f.exact_used_count,
               f.retrieved_example_count, u.email AS user_email, u.phone AS user_phone,
               u.first_name, u.last_name, u.credential_title
        FROM feedback f
        LEFT JOIN users u ON u.id = f.user_id
        WHERE 1 = 1
    """
    params = []

    if low_only:
        query += " AND COALESCE(f.feedback_score, 0) < 7"
    if note_type in ALLOWED_NOTE_TYPES:
        query += " AND f.note_type = ?"
        params.append(note_type)
    if search:
        query += " AND (LOWER(COALESCE(f.shorthand, '')) LIKE ? OR LOWER(COALESCE(f.generated_note, '')) LIKE ? OR LOWER(COALESCE(f.module_label, '')) LIKE ? OR LOWER(COALESCE(u.email, '')) LIKE ?)"
        term = f"%{search.lower()}%"
        params.extend([term, term, term, term])

    query += " ORDER BY f.created_at DESC LIMIT 20"
    cur.execute(query, params)
    rows = []
    for row in cur.fetchall():
        item = dict(row)
        item["rating_label"] = _feedback_label(item.get("rating"))
        item["feedback_score_display"] = _format_score(item.get("feedback_score"), decimals=0)
        item["user_display_name"] = _user_display_with_title(item)
        rows.append(item)
    return rows


def _fetch_feedback_prefill(feedback_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT f.id, f.shorthand, f.generated_note, f.note_type, f.module_key, f.module_label,
               f.procedure, f.rating, f.comment, u.email AS user_email
        FROM feedback f
        LEFT JOIN users u ON u.id = f.user_id
        WHERE f.id = ?
        """,
        (feedback_id,)
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    data = dict(row)
    module_label = data.get("module_label") or _module_label(data.get("module_key"))
    title_bits = [module_label or data.get("procedure") or "", _feedback_label(data.get("rating"))]
    data["suggested_title"] = " - ".join(bit for bit in title_bits if bit)
    return data


def _refresh_curriculum_pressure(conn, module_key):
    normalized_module = _normalize_module_key(module_key)
    if not normalized_module:
        return

    cur = conn.cursor()
    cur.execute(
        """
        SELECT COUNT(*) AS feedback_count,
               ROUND(AVG(COALESCE(feedback_score, 0)), 4) AS average_score
        FROM feedback
        WHERE module_key = ?
        """,
        (normalized_module,)
    )
    row = cur.fetchone()
    feedback_count = row["feedback_count"] or 0
    average_score = row["average_score"] if row["average_score"] is not None else 0.0
    normalized_gap = max(0.0, 1 - (average_score / 10.0))
    pressure = _clamp(normalized_gap * min(1.0, feedback_count / 8.0))

    cur.execute(
        """
        UPDATE scenario_templates
        SET user_feedback_score = ?,
            user_feedback_count = ?,
            curriculum_pressure = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE module_key = ?
        """,
        (average_score, feedback_count, round(pressure, 4), normalized_module)
    )


def _send_email_message(to_email, subject, body):
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT") or 587)
    smtp_user = os.getenv("SMTP_USERNAME") or os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")
    from_email = os.getenv("SMTP_FROM_EMAIL") or smtp_user

    if not smtp_host or not from_email:
        return False

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = from_email
    message["To"] = to_email
    message.set_content(body)

    with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as smtp:
        smtp.starttls()
        if smtp_user and smtp_password:
            smtp.login(smtp_user, smtp_password)
        smtp.send_message(message)
    return True


def _choose_scenario_for_trainer(cur, trainer):
    preferred_module = _normalize_module_key(trainer["preferred_module_key"])
    if preferred_module:
        cur.execute(
            """
            SELECT st.*
            FROM scenario_templates st
            WHERE st.specialty = ?
              AND st.module_key = ?
            ORDER BY st.curriculum_pressure DESC, st.next_target_level ASC, st.review_count ASC, st.updated_at DESC
            LIMIT 1
            """,
            (ACTIVE_CURRICULUM_SPECIALTY, preferred_module),
        )
        row = cur.fetchone()
        if row:
            return row

    cur.execute(
        """
        SELECT st.*
        FROM scenario_templates st
        WHERE st.specialty = ?
        ORDER BY st.curriculum_pressure DESC, st.next_target_level ASC, st.review_count ASC, COALESCE(st.module_rank, 999) ASC, st.updated_at DESC
        LIMIT 1
        """,
        (ACTIVE_CURRICULUM_SPECIALTY,),
    )
    return cur.fetchone()


def _dispatch_due_trainer_case_emails():
    smtp_ready = bool(os.getenv("SMTP_HOST") and (os.getenv("SMTP_FROM_EMAIL") or os.getenv("SMTP_USERNAME") or os.getenv("SMTP_USER")))
    if not smtp_ready:
        return {"sent": 0, "assigned": 0}

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT *
        FROM trainers
        WHERE is_active = 1
          AND send_interval_days > 0
        ORDER BY created_at ASC
        """
    )
    trainers = cur.fetchall()

    sent = 0
    assigned = 0
    now = _utcnow()

    for trainer in trainers:
        last_sent = _parse_timestamp(trainer["last_case_sent_at"])
        interval_days = max(int(trainer["send_interval_days"] or 7), 1)
        if last_sent and last_sent > now - timedelta(days=interval_days):
            continue

        scenario = _choose_scenario_for_trainer(cur, trainer)
        if not scenario:
            continue

        cur.execute(
            """
            INSERT INTO trainer_case_assignments (
                trainer_id, scenario_template_id, assignment_status, delivery_source
            )
            VALUES (?, ?, 'assigned', 'scheduled_email')
            """,
            (trainer["id"], scenario["id"])
        )
        assignment_id = cur.lastrowid
        assigned += 1

        trainer_name = trainer["name"] or trainer["email"]
        subject = f"SurgiNote trainer case: {scenario['title']}"
        body = (
            f"Hi {trainer_name},\n\n"
            f"A new training case is ready in your SurgiNote trainer portal.\n\n"
            f"Module: {scenario['module_label'] or scenario['title']}\n"
            f"Case: {scenario['title']}\n\n"
            f"Log in to review and submit your shorthand-to-gold correction.\n"
            f"{os.getenv('APP_BASE_URL', 'http://127.0.0.1:5001')}/trainer-login\n"
        )

        try:
            email_sent = _send_email_message(trainer["email"], subject, body)
        except Exception:
            email_sent = False

        if email_sent:
            sent += 1
            cur.execute(
                """
                UPDATE trainer_case_assignments
                SET email_sent_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (assignment_id,)
            )
            cur.execute(
                """
                UPDATE trainers
                SET last_case_sent_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (trainer["id"],)
            )

    conn.commit()
    conn.close()
    return {"sent": sent, "assigned": assigned}


def _promote_review_to_training_example(cur, scenario, review_id, review_row, created_by):
    scenario_map = dict(scenario)
    review_map = dict(review_row)
    cur.execute(
        """
        INSERT INTO training_examples (
            specialty, note_type, title, shorthand_input, generated_draft, corrected_output,
            status, issue_tags, editor_notes, created_by, module_key, module_label,
            scenario_template_id, scenario_review_id, source_kind
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            scenario_map["specialty"],
            scenario_map["note_type"],
            scenario_map["title"],
            review_map["shorthand_input"],
            review_map["generated_draft"],
            review_map["corrected_output"],
            review_map["quality_status"],
            review_map["issue_tags"],
            review_map["reviewer_comments"] or review_map["interpreted_lessons"],
            created_by,
            scenario_map.get("module_key"),
            scenario_map.get("module_label"),
            scenario_map["id"],
            review_id,
            "trainer_review" if review_map.get("submitted_by_trainer_id") else "scenario_review",
        )
    )
    created_training_example_id = cur.lastrowid
    cur.execute(
        "UPDATE scenario_reviews SET created_training_example_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (created_training_example_id, review_id)
    )
    return created_training_example_id


def _tokenize_similarity_text(value):
    return set(re.findall(r"[a-z0-9]{3,}", (value or "").lower()))


def _grade_to_score(grade_level):
    mapping = {
        "needs_revision": 0.2,
        "level_1_pass": 0.55,
        "level_2_pass": 0.78,
        "level_3_pass": 1.0,
    }
    return mapping.get((grade_level or "").strip(), 0.0)


def _serialize_case_facts_text(case_facts):
    try:
        return json.dumps(case_facts or {}, separators=(",", ":"), ensure_ascii=True)
    except Exception:
        return ""


def _clamp(value, minimum=0.0, maximum=1.0):
    return max(minimum, min(maximum, value))


def _sequence_similarity(left, right):
    if not left or not right:
        return 0.0
    return round(SequenceMatcher(None, left, right).ratio(), 4)


def _parse_json_array_output(raw_text):
    text = (raw_text or "").strip()
    if not text:
        raise ValueError("Empty model output.")

    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("[")
        end = text.rfind("]")
        if start == -1 or end == -1 or end <= start:
            raise
        parsed = json.loads(text[start:end + 1])

    if not isinstance(parsed, list):
        raise ValueError("Model output was not a JSON array.")
    return parsed


def _stringify_model_field(value):
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (list, tuple)):
        return "; ".join(str(item).strip() for item in value if str(item).strip()).strip()
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=True)
    return str(value).strip()


def _coerce_complexity_level(value, fallback=2):
    if isinstance(value, bool):
        return fallback
    if isinstance(value, (int, float)):
        return max(1, min(int(value), 3))
    text = str(value or "").strip()
    if not text:
        return fallback
    match = re.search(r"([1-3])", text)
    if not match:
        return fallback
    return max(1, min(int(match.group(1)), 3))


def _split_sentences(value):
    text = re.sub(r"\s+", " ", (value or "").strip())
    if not text:
        return []
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [part.strip() for part in parts if part.strip()]


def _extract_scenario_blocks(scenario_brief):
    labels = [
        "Presentation",
        "Workup",
        "Current status / surgical question",
        "Indication",
        "Intraoperative findings",
        "Procedure / disposition",
    ]
    pattern = re.compile(
        r"(?P<label>" + "|".join(re.escape(label) for label in labels) + r"):\s*",
        re.IGNORECASE,
    )
    matches = list(pattern.finditer(scenario_brief or ""))
    if not matches:
        return []

    blocks = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(scenario_brief or "")
        label = match.group("label")
        content = (scenario_brief or "")[start:end].strip()
        if content:
            blocks.append((label, content))
    return blocks


def _summarize_block(content, max_sentences=2, max_chars=320):
    chosen = []
    total_chars = 0
    for sentence in _split_sentences(content):
        if len(chosen) >= max_sentences:
            break
        projected = total_chars + len(sentence)
        if chosen and projected > max_chars:
            break
        chosen.append(sentence)
        total_chars = projected
    return " ".join(chosen) if chosen else (content or "").strip()


def _build_reviewer_packet(scenario_brief, note_type):
    blocks = _extract_scenario_blocks(scenario_brief)
    if blocks:
        lines = []
        for label, content in blocks:
            lines.append(f"{label}:")
            lines.append(_summarize_block(content))
            lines.append("")
        return "\n".join(lines).strip()

    sentences = _split_sentences(scenario_brief)
    if not sentences:
        return (scenario_brief or "").strip()

    if note_type == "op_note":
        labels = ["Indication", "Intraoperative findings", "Procedure / disposition"]
        chunks = [sentences[:2], sentences[2:4], sentences[4:6]]
    else:
        labels = ["Presentation", "Workup", "Current status / surgical question"]
        chunks = [sentences[:2], sentences[2:4], sentences[4:6]]

    lines = []
    for label, chunk in zip(labels, chunks):
        if not chunk:
            continue
        lines.append(f"{label}:")
        lines.append(" ".join(chunk))
        lines.append("")
    return "\n".join(lines).strip()


def _build_expert_request_sections(scenario_brief, request_brief):
    blocks = _extract_scenario_blocks(scenario_brief or request_brief or "")
    preferred_labels = [
        ("Presentation", "Case presentation"),
        ("Workup", "Workup"),
        ("Current status / surgical question", "Plan"),
    ]

    sections = []
    for source_label, display_label in preferred_labels:
        content = next((text for label, text in blocks if label.lower() == source_label.lower()), "")
        if content:
            sections.append({"label": display_label, "content": re.sub(r"\s+", " ", content).strip()})

    if sections:
        return sections

    fallback = (scenario_brief or request_brief or "").strip()
    if not fallback:
        return []
    return [{"label": "Scenario brief", "content": re.sub(r"\s+", " ", fallback).strip()}]


def _documentation_focus(note_type):
    focus_map = {
        "consult_note": "Focus on surgeon-like sectioning, concise phrasing, and keeping assumptions limited and believable.",
        "clinic_note": "Focus on clean interval history, concise assessment, and practical follow-up wording.",
        "op_note": "Focus on believable operative sequence, findings, and concise disposition language.",
    }
    return focus_map.get(note_type, "Focus on concise surgeon-like documentation.")


def _prepare_scenario_for_display(row):
    scenario = dict(row)
    module = GENERAL_SURGERY_MODULE_MAP.get(scenario.get("module_key") or "")
    if module:
        scenario["module_label"] = module["label"]
        scenario["module_rank"] = module["rank"]
    scenario["display_brief"] = _build_reviewer_packet(
        scenario.get("scenario_brief"),
        scenario.get("note_type"),
    )
    scenario["display_focus"] = _documentation_focus(scenario.get("note_type"))
    scenario["question_prompt"] = (scenario.get("question_prompt") or "").strip() or f"What should SurgiNote learn from this {scenario.get('note_type', 'note').replace('_', ' ')} case so the next draft sounds exactly right?"
    scenario["why_now"] = (scenario.get("why_now") or "").strip() or "This scenario targets a current uncertainty in the model's note-writing confidence."
    scenario["urgency_rank"] = scenario.get("urgency_rank") or None
    return scenario


def _interpret_review_feedback(generated_draft, corrected_output, reviewer_comments):
    comment_text = (reviewer_comments or "").strip()
    lower_comment = comment_text.lower()
    draft = (generated_draft or "").strip()
    corrected = (corrected_output or "").strip()
    edit_similarity = _sequence_similarity(draft, corrected)

    issue_tags = set()
    lessons = []

    keyword_map = {
        "verbosity": ["wordy", "verbose", "too long", "trim", "tighten", "shorter"],
        "assumption": ["assum", "unsupported", "halluc", "made up", "not stated"],
        "formatting": ["format", "heading", "section", "bullet", "underline", "paragraph"],
        "surgeon_voice": ["surgeon", "sounds like medicine", "not surgeon-like", "too academic"],
        "section_placement": ["move to", "belongs in", "put in", "under objective", "under hpi"],
        "missing_content": ["missing", "left out", "needs", "should include"],
    }

    for tag, phrases in keyword_map.items():
        if any(phrase in lower_comment for phrase in phrases):
            issue_tags.add(tag)

    if draft and corrected and len(corrected) < len(draft) * 0.82:
        issue_tags.add("verbosity")
        lessons.append("Trim unnecessary explanatory language and keep the note clinically compressed.")

    if "assumption" in issue_tags:
        lessons.append("Differentiate explicit facts from inferred wording and tighten unsupported assumptions.")
    if "section_placement" in issue_tags:
        lessons.append("Place details under the correct section heading instead of collapsing them into adjacent sections.")
    if "formatting" in issue_tags:
        lessons.append("Preserve surgeon-facing formatting with clear headings, compact paragraphs, and predictable section order.")
    if "surgeon_voice" in issue_tags:
        lessons.append("Favor surgeon-like shorthand-aware phrasing over generic medical prose.")
    if "missing_content" in issue_tags:
        lessons.append("Capture omitted high-yield clinical details when they materially affect the surgical note.")

    if comment_text and not lessons:
        lessons.append(comment_text)

    payload = {
        "issue_tags": sorted(issue_tags),
        "lessons": lessons,
        "comment_text": comment_text,
        "edit_similarity": edit_similarity,
    }
    return payload


def _get_output_typography_settings(user_id):
    font_family = (_get_user_preference(user_id, "output_font_family", "system-ui") or "system-ui").strip() or "system-ui"
    font_size = (_get_user_preference(user_id, "output_font_size", "16px") or "16px").strip() or "16px"
    return {
        "font_family": font_family,
        "font_size": font_size,
    }


def _refresh_scenario_metrics(conn, scenario_template_id):
    cur = conn.cursor()
    cur.execute(
        """
        SELECT quality_status, grade_level, edit_similarity
        FROM scenario_reviews
        WHERE scenario_template_id = ?
        """,
        (scenario_template_id,)
    )
    rows = cur.fetchall()

    total_reviews = len(rows)
    approved_reviews = sum(1 for row in rows if row["quality_status"] in {"approved", "gold"})
    gold_reviews = sum(1 for row in rows if row["quality_status"] == "gold")
    average_grade = (
        sum(_grade_to_score(row["grade_level"]) for row in rows) / total_reviews
        if total_reviews else 0.0
    )
    average_similarity = (
        sum(row["edit_similarity"] or 0 for row in rows) / total_reviews
        if total_reviews else 0.0
    )
    approval_rate = approved_reviews / total_reviews if total_reviews else 0.0
    gold_rate = gold_reviews / total_reviews if total_reviews else 0.0
    maturity_factor = min(1.0, total_reviews / 5.0)

    confidence = _clamp(
        (
            0.38 * approval_rate
            + 0.24 * average_grade
            + 0.16 * gold_rate
            + 0.22 * average_similarity
        ) * maturity_factor
    )

    if total_reviews < 2 or confidence < 0.52:
        next_target_level = 1
        scenario_status = "available"
    elif total_reviews < 4 or confidence < 0.76:
        next_target_level = 2
        scenario_status = "available"
    else:
        next_target_level = 3
        scenario_status = "covered"

    cur.execute(
        """
        UPDATE scenario_templates
        SET model_confidence = ?, review_count = ?, approved_count = ?, gold_count = ?,
            average_edit_similarity = ?, next_target_level = ?, scenario_status = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (
            round(confidence, 4),
            total_reviews,
            approved_reviews,
            gold_reviews,
            round(average_similarity, 4),
            next_target_level,
            scenario_status,
            scenario_template_id,
        )
    )


def ensure_default_scenarios(specialty_filter=None, note_type_filter=None):
    conn = get_conn()
    try:
        cur = conn.cursor()
        created = 0
        generation_errors = []
        updated = 0

        for blueprint in SCENARIO_BLUEPRINTS:
            if specialty_filter and blueprint["specialty"] != specialty_filter:
                continue
            if note_type_filter and blueprint["note_type"] != note_type_filter:
                continue

            module = GENERAL_SURGERY_MODULE_MAP.get(blueprint.get("module_key") or "")
            module_label = module["label"] if module else None
            module_rank = module["rank"] if module else None

            cur.execute(
                """
                SELECT id
                FROM scenario_templates
                WHERE specialty = ? AND note_type = ? AND title = ? AND complexity_level = ?
                """,
                (
                    blueprint["specialty"],
                    blueprint["note_type"],
                    blueprint["title"],
                    blueprint["complexity_level"],
                )
            )
            existing = cur.fetchone()
            if existing:
                cur.execute(
                    """
                    UPDATE scenario_templates
                    SET module_key = ?, module_label = ?, module_rank = ?,
                        diagnosis = ?, procedure_focus = ?, scenario_brief = ?, learning_objectives = ?,
                        structured_facts_json = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ? AND generated_by = 'seed-catalog'
                    """,
                    (
                        blueprint.get("module_key"),
                        module_label,
                        module_rank,
                        blueprint.get("diagnosis"),
                        blueprint.get("procedure_focus"),
                        blueprint["scenario_brief"],
                        blueprint.get("learning_objectives"),
                        json.dumps({**blueprint, "generated_by": "seed-catalog"}, ensure_ascii=True),
                        existing["id"],
                    )
                )
                if cur.rowcount:
                    updated += 1
                continue

            _insert_scenario_template(cur, {
                **blueprint,
                "generated_by": "seed-catalog",
            })
            created += 1

        conn.commit()
        return {"created": created, "updated": updated}
    except sqlite3.OperationalError as exc:
        conn.rollback()
        if "database is locked" in str(exc).lower():
            return {"created": 0, "updated": 0, "error": "database_locked"}
        raise
    finally:
        conn.close()


def _existing_scenario_titles(cur, specialty=None, note_type=None, module_key=None):
    query = "SELECT title FROM scenario_templates WHERE 1 = 1"
    params = []
    if specialty:
        query += " AND specialty = ?"
        params.append(specialty)
    if note_type:
        query += " AND note_type = ?"
        params.append(note_type)
    if module_key:
        query += " AND module_key = ?"
        params.append(module_key)
    query += " ORDER BY updated_at DESC, created_at DESC LIMIT 60"
    cur.execute(query, params)
    return [row["title"] for row in cur.fetchall()]


def _insert_scenario_template(cur, scenario):
    module = GENERAL_SURGERY_MODULE_MAP.get(scenario.get("module_key") or "")
    cur.execute(
        """
        INSERT INTO scenario_templates (
            specialty, note_type, title, module_key, module_label, module_rank, diagnosis, procedure_focus, complexity_level,
            scenario_status, scenario_brief, learning_objectives, structured_facts_json,
            generated_by, batch_date, urgency_rank, question_prompt, why_now
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'available', ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            scenario["specialty"],
            scenario["note_type"],
            scenario["title"],
            scenario.get("module_key"),
            (scenario.get("module_label") or (module["label"] if module else None)),
            (scenario.get("module_rank") or (module["rank"] if module else None)),
            scenario.get("diagnosis"),
            scenario.get("procedure_focus"),
            scenario["complexity_level"],
            scenario["scenario_brief"],
            scenario.get("learning_objectives"),
            json.dumps(scenario, ensure_ascii=True),
            scenario.get("generated_by", "seed-catalog"),
            scenario.get("batch_date"),
            scenario.get("urgency_rank", 0),
            scenario.get("question_prompt"),
            scenario.get("why_now"),
        )
    )


def _generate_daily_urgent_scenarios(conn, cur, limit=5, force=False):
    specialty = ACTIVE_CURRICULUM_SPECIALTY
    batch_date = _scenario_batch_date()
    existing = _daily_urgent_scenarios(cur, batch_date=batch_date, limit=limit)
    if existing and not force and len(existing) >= limit:
        return {"rows": existing, "created": 0, "batch_date": batch_date, "error": None}

    if not os.getenv("OPENAI_API_KEY"):
        return {
            "rows": existing,
            "created": 0,
            "batch_date": batch_date,
            "error": None if existing else "Missing OPENAI_API_KEY environment variable.",
        }

    created = 0
    generation_errors = []
    existing_titles = _existing_scenario_titles(cur, specialty=specialty)
    existing_title_pool = {title.lower().strip() for title in existing_titles}
    targets = _urgent_scenario_generation_targets(cur, limit=limit)
    slots_remaining = max(0, limit - len(existing))

    try:
        for target in targets:
            if slots_remaining <= 0:
                break
            module = GENERAL_SURGERY_MODULE_MAP.get(target["module_key"])
            if not module:
                continue

            try:
                prompt = build_scenario_generation_prompt(
                    specialty=specialty,
                    note_type=target["note_type"],
                    module_label=module["label"],
                    module_description=module["description"],
                    target_level=target["target_level"],
                    count=1,
                    focus=target["focus"],
                    existing_titles=existing_titles,
                )
                scenario_text, _ = call_model_and_log(
                    prompt,
                    model=DEFAULT_MODEL_NAME,
                    temperature=0.0,
                    max_output_tokens=1400,
                )
                scenario_batch = _parse_json_array_output(scenario_text)
                if not scenario_batch:
                    continue

                item = scenario_batch[0]
                title = _stringify_model_field(item.get("title"))
                question_prompt = _stringify_model_field(item.get("question_prompt"))
                scenario_brief = _stringify_model_field(item.get("scenario_brief"))
                learning_objectives = _stringify_model_field(item.get("learning_objectives"))
                why_now = _stringify_model_field(item.get("why_now")) or target.get("why_now") or ""
                diagnosis = _stringify_model_field(item.get("diagnosis"))
                procedure_focus = _stringify_model_field(item.get("procedure_focus"))

                if not title:
                    title = f"{module['label']} daily urgent scenario {len(existing) + created + 1}"
                if not question_prompt:
                    question_prompt = f"What exact shorthand and final {_note_type_label(target['note_type']).lower()} would you want for this case so SurgiNote gets {module['label']} right next time?"
                if not scenario_brief:
                    scenario_brief = "\n".join(
                        part for part in [
                            f"Presentation: {diagnosis or title}.",
                            f"Workup: Focus on the missing documentation details for {module['label']}.",
                            f"Current status / surgical question: {question_prompt}",
                        ] if part
                    ).strip()
                if not scenario_brief:
                    continue

                base_title = title
                suffix = 2
                while title.lower() in existing_title_pool:
                    title = f"{base_title} ({suffix})"
                    suffix += 1
                existing_titles.append(title)
                existing_title_pool.add(title.lower())

                _insert_scenario_template(cur, {
                    "specialty": specialty,
                    "note_type": target["note_type"],
                    "module_key": target["module_key"],
                    "module_label": module["label"],
                    "module_rank": module["rank"],
                    "title": title,
                    "diagnosis": diagnosis or None,
                    "procedure_focus": procedure_focus or None,
                    "complexity_level": _coerce_complexity_level(item.get("complexity_level"), fallback=target["target_level"]),
                    "scenario_brief": scenario_brief,
                    "learning_objectives": learning_objectives or None,
                    "generated_by": "daily-urgent-scenario-generator",
                    "focus": target["focus"],
                    "batch_date": batch_date,
                    "urgency_rank": len(existing) + created + 1,
                    "question_prompt": question_prompt,
                    "why_now": why_now,
                })
                created += 1
                slots_remaining -= 1
            except RateLimitError:
                raise
            except Exception as exc:
                generation_errors.append(str(exc))
                continue

        conn.commit()
    except RateLimitError:
        return {
            "rows": existing,
            "created": created,
            "batch_date": batch_date,
            "error": "AI scenario generation is temporarily unavailable.",
        }
    except Exception as exc:
        return {
            "rows": existing,
            "created": created,
            "batch_date": batch_date,
            "error": f"Unable to refresh urgent scenarios: {str(exc)}",
        }

    rows = _daily_urgent_scenarios(cur, batch_date=batch_date, limit=limit)
    error = None
    if not rows and generation_errors:
        error = f"Unable to refresh urgent scenarios: {generation_errors[-1]}"
    return {"rows": rows, "created": created, "batch_date": batch_date, "error": error}


def _fetch_runtime_examples(specialty, note_type, shorthand, case_facts, limit=RUNTIME_RETRIEVAL_LIMIT):
    conn = get_conn()
    cur = conn.cursor()
    specialty = _normalize_specialty(specialty)
    query_text = " ".join([
        specialty,
        note_type,
        shorthand or "",
        case_facts.get("procedure") or "",
        case_facts.get("diagnosis") or "",
        _serialize_case_facts_text(case_facts),
    ])
    query_tokens = _tokenize_similarity_text(query_text)

    candidates = []

    cur.execute(
        """
        SELECT id, specialty, note_type, title, shorthand_input, corrected_output, issue_tags,
               editor_notes, status, source_kind
        FROM training_examples
        WHERE note_type = ?
          AND status IN ('approved', 'gold')
        ORDER BY CASE WHEN specialty = ? THEN 0 ELSE 1 END, updated_at DESC, created_at DESC
        LIMIT 40
        """,
        (note_type, specialty)
    )
    for row in cur.fetchall():
        candidate_text = " ".join([
            row["specialty"] or "",
            row["title"] or "",
            row["shorthand_input"] or "",
            row["corrected_output"] or "",
            row["editor_notes"] or "",
        ])
        candidate_tokens = _tokenize_similarity_text(candidate_text)
        overlap = len(query_tokens & candidate_tokens)
        score = overlap
        if row["specialty"] == specialty:
            score += 5
        if row["status"] == "gold":
            score += 3
        if row["source_kind"] == "scenario_review":
            score += 2
        candidates.append({
            "score": score,
            "source": "training_example",
            "specialty": row["specialty"],
            "note_type": row["note_type"],
            "title": row["title"] or "Training example",
            "shorthand_input": row["shorthand_input"] or "",
            "corrected_output": row["corrected_output"] or "",
            "lessons": row["editor_notes"] or row["issue_tags"] or "",
        })

    cur.execute(
        """
        SELECT sr.id, sr.specialty, sr.note_type, sr.shorthand_input, sr.corrected_output,
               sr.interpreted_lessons, sr.issue_tags, sr.quality_status, st.title
        FROM scenario_reviews sr
        JOIN scenario_templates st ON st.id = sr.scenario_template_id
        WHERE sr.note_type = ?
          AND sr.quality_status IN ('approved', 'gold')
        ORDER BY CASE WHEN sr.specialty = ? THEN 0 ELSE 1 END, sr.updated_at DESC, sr.created_at DESC
        LIMIT 40
        """,
        (note_type, specialty)
    )
    for row in cur.fetchall():
        candidate_text = " ".join([
            row["specialty"] or "",
            row["title"] or "",
            row["shorthand_input"] or "",
            row["corrected_output"] or "",
            row["interpreted_lessons"] or "",
            row["issue_tags"] or "",
        ])
        candidate_tokens = _tokenize_similarity_text(candidate_text)
        overlap = len(query_tokens & candidate_tokens)
        score = overlap + 2
        if row["specialty"] == specialty:
            score += 5
        if row["quality_status"] == "gold":
            score += 3
        candidates.append({
            "score": score,
            "source": "scenario_review",
            "specialty": row["specialty"],
            "note_type": row["note_type"],
            "title": row["title"] or "Scenario review",
            "shorthand_input": row["shorthand_input"] or "",
            "corrected_output": row["corrected_output"] or "",
            "lessons": row["interpreted_lessons"] or row["issue_tags"] or "",
        })

    conn.close()

    unique_examples = []
    seen_outputs = set()
    for candidate in sorted(candidates, key=lambda item: item["score"], reverse=True):
        output_key = (candidate["corrected_output"] or "").strip()
        if not output_key or output_key in seen_outputs:
            continue
        seen_outputs.add(output_key)
        unique_examples.append(candidate)
        if len(unique_examples) >= limit:
            break

    return unique_examples


def build_generation_context(payload, use_user_template=True, use_training_corpus=True):
    started_at = perf_counter()
    shorthand = (payload.get("shorthand") or "").strip()
    note_type = (payload.get("note_type") or "op_note").strip()
    specialty = _normalize_specialty(payload.get("specialty"))

    if note_type not in ALLOWED_NOTE_TYPES:
        return None, jsonify({"error": "Invalid note type"}), 400

    if not shorthand:
        return None, jsonify({"error": "No shorthand provided"}), 400

    if not os.getenv("OPENAI_API_KEY"):
        return None, jsonify({"error": "Missing OPENAI_API_KEY environment variable"}), 500

    parse_started_at = perf_counter()
    case_facts = build_case_facts(shorthand)
    parse_ms = round((perf_counter() - parse_started_at) * 1000, 1)

    template_content = None
    template_profile = None
    global_tone_profile = None
    template_lookup_ms = 0.0
    if use_user_template and session.get("user_id"):
        user_id = session["user_id"]
        template_started_at = perf_counter()
        template_profile = _fetch_active_template_profile(user_id, note_type)
        global_tone_profile = _get_global_tone_profile(user_id)
        template_lookup_ms = round((perf_counter() - template_started_at) * 1000, 1)
        if template_profile and template_profile.get("strict_enabled"):
            template_content = (template_profile.get("strict_template_text") or "").strip() or None

    retrieval_started_at = perf_counter()
    retrieved_examples = []
    if use_training_corpus:
        retrieved_examples = _fetch_runtime_examples(
            specialty=specialty,
            note_type=note_type,
            shorthand=shorthand,
            case_facts=case_facts,
        )
    retrieval_ms = round((perf_counter() - retrieval_started_at) * 1000, 1)
    retrieval_source_counts = {}
    for example in retrieved_examples:
        source_key = (example.get("source_kind") or "other").strip() or "other"
        retrieval_source_counts[source_key] = retrieval_source_counts.get(source_key, 0) + 1

    prompt_started_at = perf_counter()
    prompt = build_prompt(
        case_facts=case_facts,
        note_type=note_type,
        template_content=template_content,
        specialty=specialty,
        retrieved_examples=retrieved_examples,
        template_profile=template_profile,
        global_tone_profile=global_tone_profile,
    )
    prompt_build_ms = round((perf_counter() - prompt_started_at) * 1000, 1)

    procedure_key = case_facts.get("procedure")
    procedure_label = PROCEDURE_LABELS.get(procedure_key, "Unknown")

    context = {
        "shorthand": shorthand,
        "specialty": specialty,
        "note_type": note_type,
        "case_facts": case_facts,
        "template_content": template_content,
        "template_profile": template_profile,
        "global_tone_profile": global_tone_profile,
        "prompt": prompt,
        "procedure_label": procedure_label,
        "retrieved_examples": retrieved_examples,
        "teaching_signals": {
            "template_profile_name": (template_profile or {}).get("name"),
            "strict_used": bool((template_profile or {}).get("strict_enabled")) and bool((template_profile or {}).get("strict_template_text")),
            "guide_used": bool(re.findall(r"\[\[GUIDE\]\](.*?)\[\[/GUIDE\]\]", (template_profile or {}).get("strict_template_text") or "", flags=re.IGNORECASE | re.DOTALL)),
            "global_tone_used": bool((global_tone_profile or {}).get("tone_summary")),
            "exact_block_count": len(re.findall(r"\[\[EXACT\]\](.*?)\[\[/EXACT\]\]", (template_profile or {}).get("strict_template_text") or "", flags=re.IGNORECASE | re.DOTALL)),
            "retrieved_example_count": len(retrieved_examples),
            "retrieval_source_summary": retrieval_source_counts,
        },
        "timings": {
            "parse_ms": parse_ms,
            "template_lookup_ms": template_lookup_ms,
            "retrieval_ms": retrieval_ms,
            "retrieved_example_count": len(retrieved_examples),
            "prompt_build_ms": prompt_build_ms,
            "prep_total_ms": round((perf_counter() - started_at) * 1000, 1),
        },
    }
    return context, None, None


def sse_event(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


@app.route("/login", methods=["GET", "POST"])
def login():
    return redirect(url_for("phone_login"))


@app.route("/phone-login")
@require_beta_auth
def phone_login():
    if session.get("phone_authed"):
        current_user = _current_user_row()
        if current_user and not _user_full_name(current_user):
            return redirect(url_for("complete_profile"))
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
    user_map = dict(user)

    session["beta_authed"] = True
    session["user_id"] = user_map["id"]
    session["phone"] = user_map["phone"]
    session["phone_authed"] = True
    _log_user_login(user_map["id"])
    _sync_admin_session_from_user(user_map)

    needs_profile = not _user_full_name(user_map) or not (user_map.get("credential_title") or "").strip()
    return jsonify({"status": "ok", "redirect": url_for("complete_profile" if needs_profile else "index")})


@app.route("/complete-profile", methods=["GET", "POST"])
@require_user_auth
def complete_profile():
    user = _current_user_row()
    error = None
    if request.method == "POST":
        first_name = (request.form.get("first_name") or "").strip()
        last_name = (request.form.get("last_name") or "").strip()
        credential_title = _normalize_credential_title(request.form.get("credential_title"))
        if not first_name or not last_name or credential_title not in USER_CREDENTIAL_CHOICES:
            error = "First name, last name, and credential are required."
        else:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE users
                SET first_name = ?, last_name = ?, credential_title = ?
                WHERE id = ?
                """,
                (first_name, last_name, credential_title, session["user_id"]),
            )
            conn.commit()
            conn.close()
            refreshed_user = _current_user_row()
            _sync_admin_session_from_user(refreshed_user)
            return redirect(url_for("index"))

    return render_template(
        "complete_profile.html",
        error=error,
        current_user=user,
        phone_display=_format_phone_display((user or {}).get("phone")),
        credential_choices=USER_CREDENTIAL_CHOICES,
    )


@app.route("/admin-login", methods=["GET", "POST"])
def admin_login():
    error = None
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASSWORD:
            session["admin_authed"] = True
            if session.get("user_id"):
                session["admin_id"] = session["user_id"]
            return redirect(url_for("admin"))
        error = "Incorrect password"
    return render_template("login.html", error=error, mode="admin")


@app.route("/trainer-login", methods=["GET", "POST"])
def trainer_login():
    error = None
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM trainers WHERE email = ? AND is_active = 1",
            (email,)
        )
        trainer = cur.fetchone()

        if trainer and check_password_hash(trainer["password_hash"], password):
            session["trainer_id"] = trainer["id"]
            session["trainer_email"] = trainer["email"]
            session["trainer_name"] = trainer["name"] or trainer["email"]
            cur.execute(
                "UPDATE trainers SET last_login_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (trainer["id"],)
            )
            conn.commit()
            conn.close()
            _dispatch_due_trainer_case_emails()
            return redirect(url_for("trainer_portal"))

        conn.close()
        error = "Incorrect email or password"

    return render_template("trainer_login.html", error=error)


@app.route("/trainer-reset", methods=["GET", "POST"])
def trainer_reset_request():
    status = None
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        if email:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("SELECT * FROM trainers WHERE email = ? AND is_active = 1", (email,))
            trainer = cur.fetchone()
            if trainer:
                token = secrets.token_urlsafe(24)
                expires_at = (_utcnow() + timedelta(hours=2)).isoformat()
                cur.execute(
                    """
                    UPDATE trainers
                    SET reset_token = ?, reset_token_expires_at = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (token, expires_at, trainer["id"])
                )
                conn.commit()
                reset_link = f"{os.getenv('APP_BASE_URL', 'http://127.0.0.1:5001')}/trainer-reset/{token}"
                try:
                    _send_email_message(
                        trainer["email"],
                        "Reset your SurgiNote trainer password",
                        f"Use this link to reset your password:\n\n{reset_link}\n\nThis link expires in 2 hours.",
                    )
                except Exception:
                    pass
            conn.close()
        status = "If that trainer account exists, a reset link has been sent."

    return render_template("trainer_reset_request.html", status=status)


@app.route("/trainer-reset/<token>", methods=["GET", "POST"])
def trainer_reset(token):
    error = None
    status = None

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM trainers WHERE reset_token = ? AND is_active = 1",
        (token,)
    )
    trainer = cur.fetchone()

    valid_token = bool(trainer and _parse_timestamp(trainer["reset_token_expires_at"]) and _parse_timestamp(trainer["reset_token_expires_at"]) > _utcnow())

    if request.method == "POST":
        password = request.form.get("password") or ""
        confirm_password = request.form.get("confirm_password") or ""

        if not valid_token:
            error = "Reset link is invalid or expired."
        elif len(password) < 8:
            error = "Password must be at least 8 characters."
        elif password != confirm_password:
            error = "Passwords do not match."
        else:
            cur.execute(
                """
                UPDATE trainers
                SET password_hash = ?, reset_token = NULL, reset_token_expires_at = NULL, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (generate_password_hash(password), trainer["id"])
            )
            conn.commit()
            status = "Password reset. You can now sign in."

    conn.close()
    return render_template("trainer_reset.html", error=error, status=status, valid_token=valid_token)


@app.route("/trainer-logout")
def trainer_logout():
    session.pop("trainer_id", None)
    session.pop("trainer_email", None)
    session.pop("trainer_name", None)
    return redirect(url_for("trainer_login"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("landing"))


@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


@app.route("/account", methods=["GET", "POST"])
@require_user_auth
def account_settings():
    user = _current_user_row()
    if not user:
        session.clear()
        return redirect(url_for("phone_login"))

    error = None
    status = request.args.get("status") or ""
    output_typography = _get_output_typography_settings(session["user_id"])

    if request.method == "POST":
        action = (request.form.get("action") or "save").strip()
        if action == "delete":
            confirmation = (request.form.get("delete_confirmation") or "").strip()
            if confirmation != "DELETE":
                error = "Type DELETE to confirm account deletion."
            else:
                conn = get_conn()
                cur = conn.cursor()
                user_id = session["user_id"]
                cur.execute("DELETE FROM feedback WHERE user_id = ?", (user_id,))
                cur.execute("DELETE FROM expert_requests WHERE expert_user_id = ?", (user_id,))
                cur.execute("DELETE FROM users WHERE id = ?", (user_id,))
                conn.commit()
                conn.close()
                session.clear()
                return redirect(url_for("landing"))

        first_name = (request.form.get("first_name") or "").strip()
        last_name = (request.form.get("last_name") or "").strip()
        credential_title = _normalize_credential_title(request.form.get("credential_title"))
        phone = normalize_phone(request.form.get("phone"))
        output_font_family = (request.form.get("output_font_family") or "system-ui").strip() or "system-ui"
        output_font_size = (request.form.get("output_font_size") or "16px").strip() or "16px"

        if not first_name or not last_name or credential_title not in USER_CREDENTIAL_CHOICES:
            error = "First name, last name, and credential are required."
        elif not phone:
            error = "Enter a valid phone number."
        elif output_font_family not in {value for value, _label in OUTPUT_FONT_FAMILY_CHOICES} or output_font_size not in OUTPUT_FONT_SIZE_CHOICES:
            error = "Choose valid editor text defaults."
        else:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("SELECT id FROM users WHERE phone = ? AND id != ?", (phone, session["user_id"]))
            existing = cur.fetchone()
            if existing:
                error = "That phone number is already attached to another account."
                conn.close()
            else:
                cur.execute(
                    """
                    UPDATE users
                    SET first_name = ?, last_name = ?, credential_title = ?, phone = ?
                    WHERE id = ?
                    """,
                    (first_name, last_name, credential_title, phone, session["user_id"]),
                )
                conn.commit()
                conn.close()
                refreshed_user = get_or_create_user(phone)
                session["phone"] = phone
                _sync_admin_session_from_user(refreshed_user)
                _set_user_preference(session["user_id"], "output_font_family", output_font_family)
                _set_user_preference(session["user_id"], "output_font_size", output_font_size)
                return redirect(url_for("account_settings", status="Account updated."))

    return render_template(
        "account_settings.html",
        current_user=user,
        credential_choices=USER_CREDENTIAL_CHOICES,
        output_typography=output_typography,
        output_font_family_choices=OUTPUT_FONT_FAMILY_CHOICES,
        output_font_size_choices=OUTPUT_FONT_SIZE_CHOICES,
        error=error,
        status=status,
    )


@app.route("/app")
@require_user_auth
def index():
    initial_note_type = request.args.get("note_type", "consult_note")
    if initial_note_type not in ALLOWED_NOTE_TYPES:
        initial_note_type = "consult_note"
    current_user = _current_user_row()
    if not _user_profile_complete(current_user):
        return redirect(url_for("complete_profile"))
    active_profile = _fetch_active_template_profile(session["user_id"], initial_note_type)
    global_tone_profile = _get_global_tone_profile(session["user_id"])
    output_typography = _get_output_typography_settings(session["user_id"])
    onboarding_seen = _normalize_bool(_get_user_preference(session["user_id"], "app_onboarding_seen", 0), default=False)
    recent_notes_scope = f"user-{session['user_id']}"
    return render_template(
        "index.html",
        warning=PUBLIC_WARNING,
        initial_note_type=initial_note_type,
        active_template_summary=_decorate_runtime_summary_with_global_tone(
            _template_profile_runtime_summary(active_profile),
            global_tone_profile,
        ),
        global_tone_profile=global_tone_profile,
        output_typography=output_typography,
        recent_notes_scope=recent_notes_scope,
        show_onboarding=not onboarding_seen,
        is_admin_user=bool(session.get("is_admin_user")),
        is_expert_user=bool(session.get("is_expert_user")),
        pending_expert_request_count=_pending_expert_request_count(session.get("user_id")) if session.get("is_expert_user") else 0,
        current_user=current_user,
    )


@app.route("/api/onboarding/complete", methods=["POST"])
@require_user_auth
def complete_onboarding():
    _set_user_preference(session["user_id"], "app_onboarding_seen", "1")
    return jsonify({"status": "ok"})


@app.route("/templates")
@require_user_auth
def templates_workspace():
    user_id = session["user_id"]
    selected_note_type = request.args.get("note_type", "consult_note")
    if selected_note_type not in ALLOWED_NOTE_TYPES:
        selected_note_type = "consult_note"
    current_user = _current_user_row()
    if not _user_profile_complete(current_user):
        return redirect(url_for("complete_profile"))

    profiles = _fetch_template_profiles(user_id)
    global_tone_profile = _get_global_tone_profile(user_id)
    return render_template(
        "templates_workspace.html",
        note_type_choices=NOTE_TYPE_CHOICES,
        selected_note_type=selected_note_type,
        initial_profiles=profiles,
        global_tone_profile=global_tone_profile,
        current_user=current_user,
    )


@app.route("/admin")
@require_admin_auth
def admin():
    try:
        ensure_default_scenarios()
    except sqlite3.OperationalError:
        pass

    conn = get_conn()
    cur = conn.cursor()

    rating_trend = _build_admin_rating_trend(cur, days=14)
    learning_contributions = _build_admin_learning_contributions(cur)
    recent_generated_notes = _fetch_admin_recent_generated_notes(cur, limit=50)
    user_overview_rows = _fetch_admin_user_overview(cur, limit=250)
    cur.execute(
        """
        SELECT COUNT(*) AS note_count,
               ROUND(AVG(COALESCE(feedback_score, 0)), 4) AS average_score
        FROM feedback
        """
    )
    feedback_summary = cur.fetchone()

    cur.execute("SELECT COUNT(*) AS total FROM training_examples WHERE status IN ('approved', 'gold')")
    approved_training_examples = cur.fetchone()["total"] or 0

    cur.execute("SELECT COUNT(*) AS total FROM training_examples WHERE COALESCE(in_master_canon, 0) = 1")
    master_canon_notes = cur.fetchone()["total"] or 0

    cur.execute("SELECT COUNT(*) AS total FROM expert_requests WHERE status = 'pending'")
    pending_submissions = cur.fetchone()["total"] or 0

    conn.close()

    return render_template(
        "admin_dashboard.html",
        rating_trend=rating_trend,
        learning_contributions=learning_contributions,
        recent_generated_notes=recent_generated_notes,
        user_overview_rows=user_overview_rows,
        health_summary={
            "note_count": feedback_summary["note_count"] or 0,
            "average_score": feedback_summary["average_score"] or 0,
            "average_score_display": _format_score(feedback_summary["average_score"] or 0),
            "approved_training_examples": approved_training_examples,
            "master_canon_notes": master_canon_notes,
            "pending_submissions": pending_submissions,
        },
    )


@app.route("/admin/user-access", methods=["POST"])
@require_admin_auth
def admin_user_access():
    phone = normalize_phone(request.form.get("phone"))
    grant_admin = request.form.get("grant_admin") == "1"
    grant_expert = request.form.get("grant_expert") == "1"

    if not phone:
        return redirect(url_for("admin_settings", admin_access="Enter a valid phone number."))

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE phone = ?", (phone,))
    user = cur.fetchone()

    if user:
        cur.execute(
            "UPDATE users SET is_admin = ?, is_expert = ? WHERE id = ?",
            (1 if grant_admin else 0, 1 if grant_expert else 0, user["id"])
        )
        status = "User roles updated."
    else:
        cur.execute(
            "INSERT INTO users (phone, is_admin, is_expert) VALUES (?, ?, ?)",
            (phone, 1 if grant_admin else 0, 1 if grant_expert else 0)
        )
        status = "User account created."

    conn.commit()
    conn.close()

    if session.get("phone") == phone:
        refreshed_user = get_or_create_user(phone)
        _sync_admin_session_from_user(refreshed_user)

    return redirect(url_for("admin_settings", admin_access=status))


@app.route("/admin/settings")
@require_admin_auth
def admin_settings():
    return render_template(
        "admin_settings.html",
        role_users=_role_user_rows(),
        admin_access_status=request.args.get("admin_access") or "",
    )


@app.route("/admin/trainer")
@require_admin_auth
def admin_trainer():
    prefill_feedback = None
    feedback_id = request.args.get("feedback_id")
    selected_path = (request.args.get("path") or "1").strip()
    selected_training_view = (request.args.get("view") or "").strip()
    error = request.args.get("error")
    created = request.args.get("created")
    if selected_path not in {"1", "2", "3"}:
        selected_path = "1"
    default_views = {
        "1": "live_notes",
        "2": "training_library",
        "3": "urgent_scenarios",
    }
    if not selected_training_view:
        selected_training_view = default_views[selected_path]
    if selected_path == "1" and selected_training_view == "trainer":
        selected_training_view = "live_notes"
    if feedback_id and str(feedback_id).isdigit():
        prefill_feedback = _fetch_feedback_prefill(int(feedback_id))
    conn = get_conn()
    cur = conn.cursor()
    daily_scenario_result = None
    if selected_path == "3" and selected_training_view == "urgent_scenarios":
        ensure_default_scenarios(specialty_filter=ACTIVE_CURRICULUM_SPECIALTY)
        daily_scenario_result = _generate_daily_urgent_scenarios(conn, cur, limit=5)
        if not error and daily_scenario_result.get("error"):
            error = daily_scenario_result["error"]
        if not created and daily_scenario_result.get("created"):
            created = f"Generated {daily_scenario_result['created']} fresh system-directed scenarios for today."
    training_guide = _build_admin_training_guide(cur)
    recent_feedback = _fetch_admin_recent_feedback(
        cur,
        low_only=request.args.get("low_only") == "1",
        search=(request.args.get("q") or "").strip(),
        note_type=(request.args.get("note_type") or "").strip(),
    ) if selected_path == "1" and selected_training_view == "live_notes" else []
    canonical_notes = []
    gold_examples = []
    expert_users = _expert_user_rows() if selected_path == "3" and selected_training_view == "trainer_roster" else []
    urgent_scenarios = daily_scenario_result["rows"] if daily_scenario_result else []
    expert_requests = []
    if selected_path == "2" and selected_training_view == "training_library":
        cur.execute(
            """
            SELECT id, title, note_type, module_label, corrected_output, created_at, status, editor_notes, source_kind, in_master_canon
            FROM training_examples
            WHERE COALESCE(in_master_canon, 0) = 1
               OR status IN ('approved', 'gold')
            ORDER BY COALESCE(in_master_canon, 0) DESC, updated_at DESC, created_at DESC
            LIMIT 25
            """
        )
        for row in cur.fetchall():
            item = dict(row)
            item["note_preview"] = _single_line_preview(item.get("corrected_output"), limit=180)
            item["source_label"] = _source_kind_label(item.get("source_kind"))
            canonical_notes.append(item)
    if selected_path == "2" and selected_training_view == "sample_library":
        cur.execute(
            """
            SELECT id, procedure, title, tags, ideal_note, created_at
            FROM procedure_samples
            ORDER BY created_at DESC
            LIMIT 25
            """
        )
        for row in cur.fetchall():
            item = dict(row)
            item["example_title"] = item.get("title") or item.get("procedure") or "Untitled example"
            item["example_preview"] = _single_line_preview(item.get("ideal_note"), limit=180)
            gold_examples.append(item)
    if selected_path == "3" and selected_training_view == "trainer_roster":
        cur.execute(
            """
            SELECT er.*, u.phone AS expert_phone, u.email AS expert_email,
                   u.first_name AS expert_first_name, u.last_name AS expert_last_name, u.credential_title AS expert_credential_title,
                   te.title AS training_example_title
            FROM expert_requests er
            JOIN users u ON u.id = er.expert_user_id
            LEFT JOIN training_examples te ON te.id = er.created_training_example_id
            ORDER BY CASE er.status WHEN 'pending' THEN 0 WHEN 'submitted' THEN 1 ELSE 2 END, er.created_at DESC
            """
        )
        for row in cur.fetchall():
            item = dict(row)
            item["expert_display_name"] = _user_display_with_title({
                "first_name": item.get("expert_first_name"),
                "last_name": item.get("expert_last_name"),
                "credential_title": item.get("expert_credential_title"),
            })
            item["expert_phone_display"] = _format_phone_display(item.get("expert_phone"))
            item["request_brief_preview"] = _single_line_preview(item.get("request_brief"), limit=160)
            expert_requests.append(item)
    conn.close()
    selected_training_link = None
    for lane in training_guide:
        if lane["eyebrow"] != f"Path {selected_path}":
            continue
        selected_training_link = next(
            (link for link in lane["links"] if link.get("view") == selected_training_view),
            lane["links"][0] if lane["links"] else None,
        )
        if selected_training_link and not selected_training_view:
            selected_training_view = selected_training_link.get("view", "")
        break
    return render_template(
        "admin.html",
        specialty_options=SPECIALTY_OPTIONS,
        training_statuses=TRAINING_STATUSES,
        prefill_feedback=prefill_feedback,
        training_guide=training_guide,
        selected_training_path=selected_path,
        selected_training_view=selected_training_view,
        selected_training_link=selected_training_link,
        recent_feedback=recent_feedback,
        low_only=request.args.get("low_only") == "1",
        search_query=(request.args.get("q") or "").strip(),
        selected_note_type=(request.args.get("note_type") or "").strip(),
        note_type_choices=NOTE_TYPE_CHOICES,
        canonical_notes=canonical_notes,
        gold_examples=gold_examples,
        expert_users=expert_users,
        expert_requests=expert_requests,
        urgent_scenarios=urgent_scenarios,
        curriculum_modules=_curriculum_modules(),
        scenario_batch_date=(daily_scenario_result or {}).get("batch_date"),
        error=error,
        created=created,
        return_to_trainer_hub=selected_path == "3" and selected_training_view == "trainer_roster",
    )


@app.route("/trainer")
@require_trainer_auth
def trainer_portal():
    _dispatch_due_trainer_case_emails()
    trainer_id = session.get("trainer_id")
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT * FROM trainers WHERE id = ?", (trainer_id,))
    trainer = cur.fetchone()

    cur.execute(
        """
        SELECT tca.id AS assignment_id, tca.assignment_status, tca.email_sent_at, tca.created_at AS assigned_at,
               st.id AS scenario_id, st.title, st.module_label, st.note_type, st.next_target_level,
               st.model_confidence
        FROM trainer_case_assignments tca
        JOIN scenario_templates st ON st.id = tca.scenario_template_id
        WHERE tca.trainer_id = ?
        ORDER BY tca.created_at DESC
        """,
        (trainer_id,)
    )
    assignments = cur.fetchall()

    cur.execute(
        """
        SELECT id, title, module_label, note_type, next_target_level, model_confidence
        FROM scenario_templates
        WHERE specialty = ?
        ORDER BY curriculum_pressure DESC, next_target_level ASC, COALESCE(module_rank, 999) ASC, updated_at DESC
        """,
        (ACTIVE_CURRICULUM_SPECIALTY,)
    )
    scenarios = cur.fetchall()
    conn.close()

    return render_template(
        "trainer_portal.html",
        trainer=trainer,
        assignments=assignments,
        scenarios=scenarios,
        curriculum_modules=_curriculum_modules(),
    )


@app.route("/trainer/scenarios/<int:scenario_id>", methods=["GET", "POST"])
@require_trainer_auth
def trainer_review_scenario(scenario_id):
    trainer_id = session.get("trainer_id")
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM trainers WHERE id = ?", (trainer_id,))
    trainer = cur.fetchone()

    cur.execute("SELECT * FROM scenario_templates WHERE id = ?", (scenario_id,))
    scenario = cur.fetchone()
    if not scenario:
        conn.close()
        return redirect(url_for("trainer_portal"))

    error = None
    if request.method == "POST":
        shorthand_input = (request.form.get("shorthand_input") or "").strip()
        generated_draft = (request.form.get("generated_draft") or "").strip()
        corrected_output = (request.form.get("corrected_output") or "").strip()
        reviewer_comments = (request.form.get("reviewer_comments") or "").strip()
        issue_tags = (request.form.get("issue_tags") or "").strip()

        if not shorthand_input or not corrected_output:
            error = "Shorthand input and corrected output are required."
        else:
            interpreted = _interpret_review_feedback(generated_draft, corrected_output, reviewer_comments)
            merged_tags = []
            seen_tags = set()
            for raw_tag in (issue_tags.split(",") if issue_tags else []):
                cleaned = raw_tag.strip()
                if cleaned and cleaned not in seen_tags:
                    merged_tags.append(cleaned)
                    seen_tags.add(cleaned)
            for derived_tag in interpreted["issue_tags"]:
                if derived_tag not in seen_tags:
                    merged_tags.append(derived_tag)
                    seen_tags.add(derived_tag)

            cur.execute(
                """
                INSERT INTO scenario_reviews (
                    scenario_template_id, specialty, note_type, reviewer_name, reviewer_role,
                    shorthand_input, generated_draft, corrected_output, reviewer_comments,
                    interpreted_feedback_json, interpreted_lessons, issue_tags,
                    quality_status, grade_level, review_score, edit_similarity,
                    submitted_by_trainer_id, submission_status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'draft', 'needs_revision', 0, ?, ?, 'pending')
                """,
                (
                    scenario_id,
                    scenario["specialty"],
                    scenario["note_type"],
                    trainer["name"] or trainer["email"],
                    "Trainer",
                    shorthand_input,
                    generated_draft,
                    corrected_output,
                    reviewer_comments,
                    json.dumps(interpreted, ensure_ascii=True),
                    "\n".join(interpreted["lessons"]),
                    ", ".join(merged_tags),
                    interpreted["edit_similarity"],
                    trainer_id,
                )
            )
            review_id = cur.lastrowid

            cur.execute(
                """
                UPDATE trainer_case_assignments
                SET scenario_review_id = ?, assignment_status = 'submitted', updated_at = CURRENT_TIMESTAMP
                WHERE trainer_id = ? AND scenario_template_id = ? AND assignment_status = 'assigned'
                """,
                (review_id, trainer_id, scenario_id)
            )
            conn.commit()
            conn.close()
            return redirect(url_for("trainer_portal", submitted=1))

    conn.close()
    return render_template(
        "trainer_review.html",
        scenario=_prepare_scenario_for_display(scenario),
        recent_reviews=[],
        training_statuses=TRAINING_STATUSES,
        scenario_grade_levels=SCENARIO_GRADE_LEVELS,
        error=error,
        saved=request.args.get("saved"),
        trainer=trainer,
    )


@app.route("/trainer/generate-draft", methods=["POST"])
@require_trainer_auth
def trainer_generate_training_draft():
    payload = request.get_json(silent=True) or {}
    context, error_response, status_code = build_generation_context(payload, use_user_template=False)
    if error_response:
        return error_response, status_code
    try:
        note_text, generation_meta = two_stage_generate(
            context["shorthand"],
            user_id=session.get("user_id"),
            note_type=context["note_type"],
            template_profile=context.get("template_profile"),
            training_example_id=payload.get("training_example_id"),
            specialty=context["specialty"],
            template_content=context.get("template_content"),
            retrieved_examples=context.get("retrieved_examples"),
            case_facts=context.get("case_facts"),
        )
    except GenerationLimitError as exc:
        return jsonify({"error": str(exc)}), 429
    except RateLimitError:
        return jsonify({"error": "AI generation is temporarily unavailable. Please try again shortly."}), 503
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": f"Generation failed: {str(exc)}"}), 500
    return jsonify({
        "note": note_text,
        "case_facts": context["case_facts"],
        "usage": generation_meta.get("usage", {}),
        "asserted_from_model": generation_meta.get("asserted_from_model", {}),
        "validation": generation_meta.get("validation", {}),
        "timings": context.get("timings", {}),
    })


@app.route("/expert/requests/<int:request_id>/generate-draft-stream", methods=["POST"])
@require_expert_auth
def expert_generate_request_draft_stream(request_id):
    user_id = session.get("user_id")
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, note_type
        FROM expert_requests
        WHERE id = ? AND expert_user_id = ?
        """,
        (request_id, user_id),
    )
    request_row = cur.fetchone()
    conn.close()
    if not request_row:
        return jsonify({"error": "Request not found."}), 404

    payload = request.get_json(silent=True) or {}
    payload["note_type"] = request_row["note_type"]
    context, error_response, status_code = build_generation_context(
        payload,
        use_user_template=False,
        use_training_corpus=True,
    )
    if error_response:
        return error_response, status_code

    def generate():
        yield sse_event({
            "type": "meta",
            "case_facts": context["case_facts"],
            "procedure_label": context["procedure_label"],
            "note_type": context["note_type"],
            "used_template": bool(context["template_content"]),
            "teaching_signals": context.get("teaching_signals", {}),
            "timings": context.get("timings", {}),
        })

        try:
            note_text, generation_meta = two_stage_generate(
                context["shorthand"],
                user_id=session.get("user_id"),
                note_type=context["note_type"],
                template_profile=context.get("template_profile"),
                specialty=context["specialty"],
                template_content=context.get("template_content"),
                retrieved_examples=context.get("retrieved_examples"),
                case_facts=context.get("case_facts"),
            )
            yield sse_event({"type": "delta", "delta": note_text})
            yield sse_event({
                "type": "done",
                "timings": context.get("timings", {}),
                "usage": generation_meta.get("usage", {}),
                "asserted_from_model": generation_meta.get("asserted_from_model", {}),
                "validation": generation_meta.get("validation", {}),
            })
        except GenerationLimitError as exc:
            yield sse_event({"type": "error", "error": str(exc)})
        except RateLimitError:
            yield sse_event({"type": "error", "error": "AI generation is temporarily unavailable. Please try again shortly."})
        except ValueError as exc:
            yield sse_event({"type": "error", "error": str(exc)})
        except Exception as exc:
            yield sse_event({"type": "error", "error": f"Generation failed: {str(exc)}"})

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.route("/expert/requests")
@require_expert_auth
def expert_requests_portal():
    user_id = session.get("user_id")
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT er.*, st.title AS scenario_title, st.scenario_brief
        FROM expert_requests er
        LEFT JOIN scenario_templates st ON st.id = er.scenario_template_id
        WHERE er.expert_user_id = ?
        ORDER BY CASE er.status WHEN 'pending' THEN 0 WHEN 'submitted' THEN 1 ELSE 2 END, er.created_at DESC
        """,
        (user_id,),
    )
    requests = []
    for row in cur.fetchall():
        item = dict(row)
        item["brief_sections"] = _build_expert_request_sections(
            item.get("scenario_brief"),
            item.get("request_brief"),
        )
        requests.append(item)
    conn.close()
    return render_template(
        "expert_requests.html",
        expert_requests=requests,
        pending_request_count=sum(1 for row in requests if row["status"] == "pending"),
    )


@app.route("/expert/requests/<int:request_id>/submit", methods=["POST"])
@require_expert_auth
def submit_expert_request(request_id):
    user_id = session.get("user_id")
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT er.*, u.phone, u.email
        FROM expert_requests er
        JOIN users u ON u.id = er.expert_user_id
        WHERE er.id = ? AND er.expert_user_id = ?
        """,
        (request_id, user_id),
    )
    expert_request = cur.fetchone()
    if not expert_request:
        conn.close()
        return redirect(url_for("expert_requests_portal"))

    shorthand_input = (request.form.get("shorthand_input") or "").strip()
    corrected_output = (request.form.get("corrected_output") or "").strip()
    generated_draft = (request.form.get("generated_draft") or "").strip()
    expert_notes = (request.form.get("expert_notes") or "").strip()
    accepted_assumptions_json = (request.form.get("accepted_assumptions_json") or "[]").strip() or "[]"

    if not shorthand_input or not corrected_output:
        conn.close()
        return redirect(url_for("expert_requests_portal", error="Shorthand input and tracked revision are required."))

    expert_user = {
        "id": user_id,
        "phone": expert_request["phone"],
        "email": expert_request["email"],
    }
    created_example_id = _create_training_example_from_expert_request(
        cur,
        expert_request,
        expert_user,
        {
            "title": expert_request["title"],
            "note_type": expert_request["note_type"],
            "shorthand_input": shorthand_input,
            "generated_draft": generated_draft,
            "corrected_output": corrected_output,
            "expert_notes": expert_notes,
            "accepted_assumptions_json": accepted_assumptions_json,
        },
    )
    cur.execute(
        """
        UPDATE expert_requests
        SET shorthand_input = ?, generated_draft = ?, corrected_output = ?, expert_notes = ?, accepted_assumptions_json = ?,
            created_training_example_id = ?, status = 'submitted', submitted_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (
            shorthand_input,
            generated_draft or None,
            corrected_output,
            expert_notes or None,
            accepted_assumptions_json,
            created_example_id,
            request_id,
        ),
    )
    conn.commit()
    conn.close()
    return redirect(url_for("expert_requests_portal", submitted=1))


@app.route("/admin/trainers", methods=["GET", "POST"])
@require_admin_auth
def admin_trainers():
    error = None
    return_to = (request.form.get("return_to") or "").strip()

    if request.method == "POST":
        try:
            expert_user_id = int(request.form.get("expert_user_id") or 0)
        except ValueError:
            expert_user_id = 0
        request_kind = (request.form.get("request_kind") or "gold_standard_note").strip()
        title = (request.form.get("title") or "").strip()
        note_type = (request.form.get("note_type") or "consult_note").strip()
        module_key = _normalize_module_key(request.form.get("module_key"))
        request_brief = (request.form.get("request_brief") or "").strip()
        raw_scenario_id = (request.form.get("scenario_template_id") or "").strip()
        scenario_template_id = int(raw_scenario_id) if raw_scenario_id.isdigit() else None

        if request_kind not in EXPERT_REQUEST_KINDS:
            request_kind = "gold_standard_note"
        if note_type not in ALLOWED_NOTE_TYPES:
            note_type = "consult_note"

        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, phone, email FROM users WHERE id = ? AND COALESCE(is_expert, 0) = 1",
            (expert_user_id,),
        )
        expert_user = cur.fetchone()

        scenario = None
        if scenario_template_id:
            cur.execute(
                """
                SELECT id, title, note_type, module_key, module_label, scenario_brief
                FROM scenario_templates
                WHERE id = ?
                """,
                (scenario_template_id,),
            )
            scenario = cur.fetchone()

        if not expert_user:
            error = "Choose a SurgiNote Expert before assigning work."
        elif not title and not scenario:
            error = "Add a title or pick a scenario to assign."
        elif not request_brief and not scenario:
            error = "Include a clear request brief for the expert."
        else:
            resolved_note_type = scenario["note_type"] if scenario else note_type
            resolved_module_key = scenario["module_key"] if scenario else module_key
            resolved_module_label = scenario["module_label"] if scenario else _module_label(module_key)
            resolved_title = scenario["title"] if scenario else title
            resolved_brief = scenario["scenario_brief"] if scenario else request_brief
            cur.execute(
                """
                INSERT INTO expert_requests (
                    expert_user_id, requested_by_admin_id, request_kind, title, note_type, module_key,
                    module_label, scenario_template_id, request_brief
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    expert_user_id,
                    session.get("admin_id"),
                    request_kind,
                    resolved_title,
                    resolved_note_type,
                    resolved_module_key,
                    resolved_module_label,
                    scenario["id"] if scenario else None,
                    resolved_brief,
                ),
            )
            conn.commit()
            conn.close()
            if return_to == "trainer_hub":
                return redirect(url_for("admin_trainer", path=3, view="trainer_roster", created=1))
            return redirect(url_for("admin_trainers", created=1))
        conn.close()
        if return_to == "trainer_hub":
            return redirect(url_for("admin_trainer", path=3, view="trainer_roster", error=error))

    conn = get_conn()
    cur = conn.cursor()
    expert_users = _expert_user_rows()
    urgent_scenarios = _top_urgent_scenarios(cur, limit=5)
    cur.execute(
        """
        SELECT er.*, u.phone AS expert_phone, u.email AS expert_email,
               u.first_name AS expert_first_name, u.last_name AS expert_last_name, u.credential_title AS expert_credential_title,
               te.title AS training_example_title
        FROM expert_requests er
        JOIN users u ON u.id = er.expert_user_id
        LEFT JOIN training_examples te ON te.id = er.created_training_example_id
        ORDER BY CASE er.status WHEN 'pending' THEN 0 WHEN 'submitted' THEN 1 ELSE 2 END, er.created_at DESC
        """
    )
    expert_requests = []
    for row in cur.fetchall():
        item = dict(row)
        item["expert_display_name"] = _user_display_with_title({
            "first_name": item.get("expert_first_name"),
            "last_name": item.get("expert_last_name"),
            "credential_title": item.get("expert_credential_title"),
        })
        item["expert_phone_display"] = _format_phone_display(item.get("expert_phone"))
        item["request_brief_preview"] = _single_line_preview(item.get("request_brief"), limit=160)
        expert_requests.append(item)
    conn.close()
    return render_template(
        "admin_trainers.html",
        expert_users=expert_users,
        expert_requests=expert_requests,
        urgent_scenarios=urgent_scenarios,
        curriculum_modules=_curriculum_modules(),
        error=error,
        created=request.args.get("created"),
    )


@app.route("/admin/trainers/requests/<int:request_id>/cancel", methods=["POST"])
@require_admin_auth
def cancel_expert_request(request_id):
    return_to = (request.form.get("return_to") or "").strip()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM expert_requests WHERE id = ? AND status = 'pending'",
        (request_id,),
    )
    conn.commit()
    deleted = cur.rowcount or 0
    conn.close()

    message = "Request canceled." if deleted else "Only pending requests can be canceled."
    if return_to == "trainer_hub":
        return redirect(url_for("admin_trainer", path=3, view="trainer_roster", created=message))
    return redirect(url_for("admin_trainers", created=message))


@app.route("/admin/trainer/canonical-notes", methods=["POST"])
@require_admin_auth
def create_canonical_note():
    note_type = (request.form.get("note_type") or "consult_note").strip()
    descriptor = (request.form.get("descriptor") or "").strip()
    title = (request.form.get("title") or "").strip()
    raw_note = (request.form.get("canonical_note_text") or "").strip()

    if note_type not in ALLOWED_NOTE_TYPES:
        note_type = "consult_note"

    if not raw_note:
        return redirect(url_for("admin_trainer", path=2, view="training_library", error="Paste a note to save it into the Master Note Canon."))

    scrubbed_note, replacement_count = _deidentify_phi_text(raw_note)
    if not scrubbed_note:
        return redirect(url_for("admin_trainer", path=2, view="training_library", error="The note was empty after de-identification."))

    resolved_title = title or _canonical_note_title(scrubbed_note, note_type)
    created_by = session.get("phone") or session.get("user_email") or f"admin-{session.get('admin_id') or 'unknown'}"
    module_key = _infer_feedback_module(
        note_type,
        " ".join([descriptor, raw_note]),
        generated_note=resolved_title,
    )
    module_label = _module_label(module_key)
    editor_note = "Canonical EMR note intake."
    if descriptor:
        editor_note += f" Descriptor: {descriptor}."
    if replacement_count:
        editor_note += f" PHI scrub pass replaced {replacement_count} field{'s' if replacement_count != 1 else ''}."

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO training_examples (
            specialty, note_type, title, shorthand_input, generated_draft, corrected_output,
            status, issue_tags, editor_notes, created_by, module_key, module_label, source_kind, in_master_canon
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
        """,
        (
            ACTIVE_CURRICULUM_SPECIALTY,
            note_type,
            resolved_title,
            scrubbed_note,
            None,
            scrubbed_note,
            "gold",
            "canonical-note",
            editor_note,
            created_by,
            module_key,
            module_label,
            "canonical_note",
        ),
    )
    conn.commit()
    conn.close()

    status = "Master note canon entry saved."
    if replacement_count:
        status += f" Extra PHI scrub applied to {replacement_count} field{'s' if replacement_count != 1 else ''}."
    return redirect(url_for("admin_trainer", path=2, view="training_library", created=status))


@app.route("/admin/training-examples/<int:feedback_id>/promote-to-canon", methods=["POST"])
@require_admin_auth
def promote_feedback_note_to_canon(feedback_id):
    payload = request.get_json(silent=True) or {}

    specialty = (payload.get("specialty") or "").strip()
    note_type = (payload.get("note_type") or "consult_note").strip()
    title = (payload.get("title") or "").strip()
    shorthand_input = (payload.get("shorthand_input") or "").strip()
    generated_draft = (payload.get("generated_draft") or "").strip()
    corrected_output = (payload.get("corrected_output") or "").strip()
    status = (payload.get("status") or "approved").strip()
    issue_tags = payload.get("issue_tags", [])
    editor_notes = (payload.get("editor_notes") or "").strip()
    accepted_assumptions_json = (payload.get("accepted_assumptions_json") or "[]").strip() or "[]"
    module_key = _normalize_module_key(payload.get("module_key"))
    module_label = GENERAL_SURGERY_MODULE_MAP.get(module_key, {}).get("label") if module_key else None

    if note_type not in ALLOWED_NOTE_TYPES:
        return jsonify({"error": "Invalid note type"}), 400
    if status not in TRAINING_STATUSES:
        return jsonify({"error": "Invalid training status"}), 400
    if not specialty or not shorthand_input or not corrected_output:
        return jsonify({"error": "Specialty, shorthand input, and corrected output are required"}), 400

    issue_tags_str = ", ".join(issue_tags) if isinstance(issue_tags, list) else str(issue_tags or "")
    canon_title = title or _canonical_note_title(corrected_output, note_type)

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id FROM feedback WHERE id = ?", (feedback_id,))
    if not cur.fetchone():
        conn.close()
        return jsonify({"error": "Live note not found."}), 404

    cur.execute(
        """
        SELECT id
        FROM training_examples
        WHERE source_kind = 'admin-review'
          AND COALESCE(in_master_canon, 0) = 1
          AND shorthand_input = ?
          AND corrected_output = ?
        LIMIT 1
        """,
        (shorthand_input, corrected_output),
    )
    existing = cur.fetchone()
    if existing:
        cur.execute(
            """
            UPDATE training_examples
            SET specialty = ?,
                note_type = ?,
                title = ?,
                generated_draft = ?,
                corrected_output = ?,
                status = ?,
                issue_tags = ?,
                editor_notes = ?,
                module_key = ?,
                module_label = ?,
                accepted_assumptions_json = ?,
                in_master_canon = 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                specialty,
                note_type,
                canon_title,
                generated_draft,
                corrected_output,
                status,
                issue_tags_str,
                editor_notes,
                module_key or None,
                module_label,
                accepted_assumptions_json,
                existing["id"],
            ),
        )
        conn.commit()
        conn.close()
        return jsonify({"status": "ok"})

    cur.execute(
        """
        INSERT INTO training_examples (
            specialty, note_type, title, shorthand_input, generated_draft, corrected_output,
            status, issue_tags, editor_notes, created_by, module_key, module_label,
            accepted_assumptions_json, source_kind, in_master_canon
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
        """,
        (
            specialty,
            note_type,
            canon_title,
            shorthand_input,
            generated_draft,
            corrected_output,
            status,
            issue_tags_str,
            editor_notes,
            "admin-team",
            module_key or None,
            module_label,
            accepted_assumptions_json,
            "admin-review",
        )
    )
    conn.commit()
    conn.close()

    return jsonify({"status": "ok"})


@app.route("/admin/feedback/<int:feedback_id>/add-to-canon", methods=["POST"])
@require_admin_auth
def add_feedback_note_to_canon(feedback_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, shorthand, generated_note, note_type, module_key, module_label,
               procedure, rating, comment
        FROM feedback
        WHERE id = ?
        """,
        (feedback_id,),
    )
    row = cur.fetchone()
    if not row:
        conn.close()
        return redirect(url_for("admin_trainer", path=1, view="live_notes", error="Live note not found."))

    item = dict(row)
    shorthand_input = (item.get("shorthand") or "").strip()
    corrected_output = (item.get("generated_note") or "").strip()
    note_type = (item.get("note_type") or "consult_note").strip()
    module_key = _normalize_module_key(item.get("module_key"))
    module_label = item.get("module_label") or _module_label(module_key)

    if note_type not in ALLOWED_NOTE_TYPES:
        note_type = "consult_note"

    if not shorthand_input or not corrected_output:
        conn.close()
        return redirect(
            url_for(
                "admin_trainer",
                path=1,
                view="live_notes",
                error="This live note is missing shorthand or generated output, so it could not be added to the canon.",
            )
        )

    canon_title = _canonical_note_title(
        corrected_output,
        note_type,
    ) or "Canon note"
    if module_label:
        canon_title = f"{module_label} - {canon_title}"

    issue_tags = ["direct-canon", "rated-live-note"]
    if item.get("rating"):
        issue_tags.append(str(item["rating"]).strip())
    issue_tags_str = ", ".join(bit for bit in issue_tags if bit)

    editor_notes_parts = ["Promoted directly from a rated live note by admin."]
    if item.get("comment"):
        editor_notes_parts.append(f"Original rating comment: {str(item['comment']).strip()}")
    editor_notes = "\n\n".join(editor_notes_parts)

    cur.execute(
        """
        SELECT id
        FROM training_examples
        WHERE COALESCE(in_master_canon, 0) = 1
          AND shorthand_input = ?
          AND corrected_output = ?
        LIMIT 1
        """,
        (shorthand_input, corrected_output),
    )
    existing = cur.fetchone()
    if existing:
        cur.execute(
            """
            UPDATE training_examples
            SET specialty = ?,
                note_type = ?,
                title = ?,
                status = 'approved',
                issue_tags = ?,
                editor_notes = ?,
                module_key = ?,
                module_label = ?,
                source_kind = 'admin-review',
                in_master_canon = 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                ACTIVE_CURRICULUM_SPECIALTY,
                note_type,
                canon_title,
                issue_tags_str,
                editor_notes,
                module_key or None,
                module_label,
                existing["id"],
            ),
        )
        conn.commit()
        conn.close()
        return redirect(url_for("admin_trainer", path=1, view="live_notes", created="Note is already in the Master Note Canon."))

    cur.execute(
        """
        INSERT INTO training_examples (
            specialty, note_type, title, shorthand_input, generated_draft, corrected_output,
            status, issue_tags, editor_notes, created_by, module_key, module_label,
            source_kind, in_master_canon
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
        """,
        (
            ACTIVE_CURRICULUM_SPECIALTY,
            note_type,
            canon_title,
            shorthand_input,
            corrected_output,
            corrected_output,
            "approved",
            issue_tags_str,
            editor_notes,
            "admin-team",
            module_key or None,
            module_label,
            "admin-review",
        ),
    )
    conn.commit()
    conn.close()
    return redirect(url_for("admin_trainer", path=1, view="live_notes", created="Added to Master Note Canon."))


@app.route("/admin/trainers/<int:trainer_id>/update", methods=["POST"])
@require_admin_auth
def update_trainer(trainer_id):
    is_active = 1 if request.form.get("is_active") == "on" else 0
    try:
        send_interval_days = max(int(request.form.get("send_interval_days") or 7), 1)
    except ValueError:
        send_interval_days = 7
    preferred_module_key = _normalize_module_key(request.form.get("preferred_module_key"))

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE trainers
        SET is_active = ?, send_interval_days = ?, preferred_module_key = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (is_active, send_interval_days, preferred_module_key or None, trainer_id)
    )
    conn.commit()
    conn.close()
    return redirect(url_for("admin_trainers", updated=1))


@app.route("/admin/trainers/dispatch", methods=["POST"])
@require_admin_auth
def dispatch_trainer_cases():
    result = _dispatch_due_trainer_case_emails()
    return redirect(url_for("admin_trainers", dispatched=result["sent"]))


@app.route("/admin/trainer-submissions")
@require_admin_auth
def admin_trainer_submissions():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT er.id, er.created_at, er.status AS submission_status, er.title AS scenario_title,
               er.module_label, er.note_type, er.request_kind, u.phone AS expert_phone, u.email AS expert_email,
               u.first_name AS expert_first_name, u.last_name AS expert_last_name, u.credential_title AS expert_credential_title,
               te.id AS training_example_id
        FROM expert_requests er
        JOIN users u ON u.id = er.expert_user_id
        LEFT JOIN training_examples te ON te.id = er.created_training_example_id
        WHERE er.status IN ('submitted', 'completed')
        ORDER BY CASE WHEN er.status = 'submitted' THEN 0 ELSE 1 END, er.created_at DESC
        """
    )
    submissions = []
    for row in cur.fetchall():
        item = dict(row)
        item["expert_display_name"] = _user_display_with_title({
            "first_name": item.get("expert_first_name"),
            "last_name": item.get("expert_last_name"),
            "credential_title": item.get("expert_credential_title"),
        })
        submissions.append(item)
    conn.close()
    return render_template("trainer_submissions.html", submissions=submissions)


@app.route("/admin/trainer-submissions/<int:review_id>", methods=["GET", "POST"])
@require_admin_auth
def admin_review_trainer_submission(review_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT sr.*, st.title AS scenario_title, st.module_key, st.module_label, st.specialty, st.note_type,
               st.diagnosis, st.procedure_focus, st.complexity_level, st.next_target_level, st.model_confidence,
               st.scenario_brief,
               t.name AS trainer_name, t.email AS trainer_email
        FROM scenario_reviews sr
        JOIN scenario_templates st ON st.id = sr.scenario_template_id
        LEFT JOIN trainers t ON t.id = sr.submitted_by_trainer_id
        WHERE sr.id = ?
        """,
        (review_id,)
    )
    review = cur.fetchone()
    if not review:
        conn.close()
        return redirect(url_for("admin_trainer_submissions"))

    scenario = {
        "id": review["scenario_template_id"],
        "specialty": review["specialty"],
        "note_type": review["note_type"],
        "title": review["scenario_title"],
        "module_key": review["module_key"],
        "module_label": review["module_label"],
        "diagnosis": review["diagnosis"],
        "procedure_focus": review["procedure_focus"],
        "complexity_level": review["complexity_level"],
        "next_target_level": review["next_target_level"],
        "model_confidence": review["model_confidence"],
        "scenario_brief": review["scenario_brief"],
        "review_count": 0,
        "approved_count": 0,
        "gold_count": 0,
    }

    error = None
    if request.method == "POST":
        action = (request.form.get("action") or "approve").strip()
        corrected_output = (request.form.get("corrected_output") or "").strip()
        reviewer_comments = (request.form.get("reviewer_comments") or "").strip()
        issue_tags = (request.form.get("issue_tags") or "").strip()
        quality_status = (request.form.get("quality_status") or "approved").strip()
        grade_level = (request.form.get("grade_level") or "level_1_pass").strip()
        admin_review_notes = (request.form.get("admin_review_notes") or "").strip()

        if action == "approve" and not corrected_output:
            error = "Corrected output is required to approve a submission."
        else:
            interpreted = _interpret_review_feedback(review["generated_draft"], corrected_output or review["corrected_output"], reviewer_comments or review["reviewer_comments"])
            submission_status = "approved" if action == "approve" else "rejected"
            review_score = round(
                (0.6 * _grade_to_score(grade_level) + 0.4 * (1.0 if quality_status in {"approved", "gold"} else 0.35)),
                4,
            ) if action == "approve" else 0

            cur.execute(
                """
                UPDATE scenario_reviews
                SET corrected_output = ?, reviewer_comments = ?, issue_tags = ?, quality_status = ?, grade_level = ?,
                    review_score = ?, edit_similarity = ?, interpreted_feedback_json = ?, interpreted_lessons = ?,
                    submission_status = ?, admin_review_notes = ?, reviewed_by_admin_id = ?, reviewed_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    corrected_output or review["corrected_output"],
                    reviewer_comments or review["reviewer_comments"],
                    issue_tags,
                    quality_status if action == "approve" else "needs_review",
                    grade_level if action == "approve" else "needs_revision",
                    review_score,
                    interpreted["edit_similarity"] if action == "approve" else review["edit_similarity"],
                    json.dumps(interpreted, ensure_ascii=True),
                    "\n".join(interpreted["lessons"]),
                    submission_status,
                    admin_review_notes,
                    session.get("admin_id", 1),
                    review_id,
                )
            )

            if action == "approve" and not review["created_training_example_id"]:
                promoted_review = dict(review)
                promoted_review["corrected_output"] = corrected_output or review["corrected_output"]
                promoted_review["reviewer_comments"] = reviewer_comments or review["reviewer_comments"]
                promoted_review["issue_tags"] = issue_tags
                promoted_review["quality_status"] = quality_status
                _promote_review_to_training_example(cur, scenario, review_id, promoted_review, "admin-review")
                _refresh_scenario_metrics(conn, scenario["id"])

            cur.execute(
                """
                UPDATE trainer_case_assignments
                SET assignment_status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE scenario_review_id = ?
                """,
                ("approved" if action == "approve" else "rejected", review_id)
            )
            conn.commit()
            conn.close()
            return redirect(url_for("admin_trainer_submissions", reviewed=1))

    conn.close()
    return render_template(
        "admin_submission_review.html",
        scenario=_prepare_scenario_for_display(scenario),
        training_statuses=TRAINING_STATUSES,
        scenario_grade_levels=SCENARIO_GRADE_LEVELS,
        error=error,
        saved=request.args.get("saved"),
        submission=review,
    )


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


@app.route("/api/template-profiles", methods=["GET"])
@require_user_auth
def list_template_profiles():
    note_type = (request.args.get("note_type") or "").strip()
    if note_type and note_type not in ALLOWED_NOTE_TYPES:
        return jsonify({"error": "Invalid note type"}), 400

    profiles = _fetch_template_profiles(session["user_id"], note_type=note_type or None)
    return jsonify({"profiles": profiles})


@app.route("/api/tone-profile", methods=["GET"])
@require_user_auth
def get_tone_profile():
    return jsonify({"profile": _get_global_tone_profile(session["user_id"])})


@app.route("/api/tone-profile", methods=["POST"])
@require_user_auth
def save_tone_profile():
    payload = request.get_json(silent=True) or {}
    notes_text = (payload.get("notes_text") or "").strip()
    if not notes_text:
        return jsonify({"error": "Paste a few de-identified notes first."}), 400

    try:
        summary = _build_tone_summary_from_notes(notes_text)
    except Exception as exc:
        return jsonify({"error": f"Unable to analyze tone: {str(exc)}"}), 500

    profile = {
        "notes_text": notes_text,
        "tone_summary": summary.get("tone_summary") or "",
        "tone_traits": summary.get("tone_traits") or [],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    _set_user_preference(session["user_id"], "global_tone_profile", json.dumps(profile))
    return jsonify({"status": "ok", "profile": profile})


@app.route("/api/tone-profile", methods=["DELETE"])
@require_user_auth
def delete_tone_profile():
    _delete_user_preference(session["user_id"], "global_tone_profile")
    return jsonify({"status": "ok"})


@app.route("/api/template-profiles/active/<note_type>", methods=["GET"])
@require_user_auth
def get_active_template_profile(note_type):
    if note_type not in ALLOWED_NOTE_TYPES:
        return jsonify({"error": "Invalid note type"}), 400

    profile = _fetch_active_template_profile(session["user_id"], note_type)
    return jsonify({
        "profile": _decorate_runtime_summary_with_global_tone(
            _template_profile_runtime_summary(profile),
            _get_global_tone_profile(session["user_id"]),
        )
    })


@app.route("/api/template-profiles", methods=["POST"])
@require_user_auth
def create_template_profile():
    payload = request.get_json(silent=True) or {}
    note_type = (payload.get("note_type") or "").strip()
    name = (payload.get("name") or "").strip()
    strict_template_text = (payload.get("strict_template_text") or "").strip()
    style_example_text = (payload.get("style_example_text") or "").strip()
    strict_template_html = (payload.get("strict_template_html") or "").strip()
    style_example_html = (payload.get("style_example_html") or "").strip()
    output_font_family = (payload.get("output_font_family") or "system-ui").strip() or "system-ui"
    output_font_size = (payload.get("output_font_size") or "16px").strip() or "16px"
    strict_enabled = 1 if _normalize_bool(payload.get("strict_enabled"), default=True) else 0
    style_enabled = 0
    is_default = 1 if _normalize_bool(payload.get("is_default"), default=False) else 0

    if note_type not in ALLOWED_NOTE_TYPES:
        return jsonify({"error": "Invalid note type"}), 400
    if not name:
        return jsonify({"error": "Profile name is required"}), 400
    if not strict_template_text:
        return jsonify({"error": "Paste a de-identified note or EMR template and mark what SurgiNote should learn."}), 400

    user_id = session["user_id"]
    _ensure_legacy_template_profiles(user_id)

    conn = get_conn()
    cur = conn.cursor()
    if is_default:
        cur.execute(
            "UPDATE template_profiles SET is_default = 0, updated_at = CURRENT_TIMESTAMP WHERE user_id = ? AND note_type = ?",
            (user_id, note_type),
        )
    else:
        cur.execute(
            "SELECT COUNT(*) AS total FROM template_profiles WHERE user_id = ? AND note_type = ?",
            (user_id, note_type),
        )
        if (cur.fetchone()["total"] or 0) == 0:
            is_default = 1

    cur.execute(
        """
        INSERT INTO template_profiles (
            user_id, note_type, name, strict_template_text, strict_enabled,
            style_example_text, style_enabled, is_default, updated_at,
            strict_template_html, style_example_html, output_font_family, output_font_size
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?, ?)
        """,
        (
            user_id,
            note_type,
            name,
            strict_template_text,
            strict_enabled,
            style_example_text,
            style_enabled,
            is_default,
            strict_template_html,
            style_example_html,
            output_font_family,
            output_font_size,
        )
    )
    profile_id = cur.lastrowid
    conn.commit()
    conn.close()
    return jsonify({"status": "ok", "profile": _fetch_template_profile_by_id(user_id, profile_id)})


@app.route("/api/template-profiles/<int:profile_id>", methods=["GET"])
@require_user_auth
def get_template_profile(profile_id):
    profile = _fetch_template_profile_by_id(session["user_id"], profile_id)
    if not profile:
        return jsonify({"error": "Template profile not found"}), 404
    return jsonify({"profile": profile})


@app.route("/api/template-profiles/<int:profile_id>", methods=["POST"])
@require_user_auth
def update_template_profile(profile_id):
    payload = request.get_json(silent=True) or {}
    existing = _fetch_template_profile_by_id(session["user_id"], profile_id)
    if not existing:
        return jsonify({"error": "Template profile not found"}), 404

    name = (payload.get("name") or "").strip()
    strict_template_text = (payload.get("strict_template_text") or "").strip()
    style_example_text = (payload.get("style_example_text") or "").strip()
    strict_template_html = (payload.get("strict_template_html") or "").strip()
    style_example_html = (payload.get("style_example_html") or "").strip()
    output_font_family = (payload.get("output_font_family") or existing.get("output_font_family") or "system-ui").strip() or "system-ui"
    output_font_size = (payload.get("output_font_size") or existing.get("output_font_size") or "16px").strip() or "16px"
    strict_enabled = 1 if _normalize_bool(payload.get("strict_enabled"), default=bool(existing["strict_enabled"])) else 0
    style_enabled = 0
    is_default = 1 if _normalize_bool(payload.get("is_default"), default=bool(existing["is_default"])) else 0

    if not name:
        return jsonify({"error": "Profile name is required"}), 400
    if not strict_template_text:
        return jsonify({"error": "Paste a de-identified note or EMR template and mark what SurgiNote should learn."}), 400

    user_id = session["user_id"]
    conn = get_conn()
    cur = conn.cursor()
    if is_default:
        cur.execute(
            "UPDATE template_profiles SET is_default = 0, updated_at = CURRENT_TIMESTAMP WHERE user_id = ? AND note_type = ?",
            (user_id, existing["note_type"]),
        )

    cur.execute(
        """
        UPDATE template_profiles
        SET name = ?, strict_template_text = ?, strict_enabled = ?, style_example_text = ?,
            style_enabled = ?, is_default = ?, strict_template_html = ?, style_example_html = ?,
            output_font_family = ?, output_font_size = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ? AND user_id = ?
        """,
        (
            name,
            strict_template_text,
            strict_enabled,
            style_example_text,
            style_enabled,
            is_default,
            strict_template_html,
            style_example_html,
            output_font_family,
            output_font_size,
            profile_id,
            user_id,
        )
    )
    conn.commit()
    conn.close()
    return jsonify({"status": "ok", "profile": _fetch_template_profile_by_id(user_id, profile_id)})


@app.route("/api/template-profiles/<int:profile_id>/default", methods=["POST"])
@require_user_auth
def set_default_template_profile(profile_id):
    profile = _fetch_template_profile_by_id(session["user_id"], profile_id)
    if not profile:
        return jsonify({"error": "Template profile not found"}), 404

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE template_profiles SET is_default = 0, updated_at = CURRENT_TIMESTAMP WHERE user_id = ? AND note_type = ?",
        (session["user_id"], profile["note_type"]),
    )
    cur.execute(
        "UPDATE template_profiles SET is_default = 1, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND user_id = ?",
        (profile_id, session["user_id"]),
    )
    conn.commit()
    conn.close()
    return jsonify({"status": "ok", "profile": _fetch_template_profile_by_id(session["user_id"], profile_id)})


@app.route("/api/template-profiles/<int:profile_id>", methods=["DELETE"])
@require_user_auth
def delete_template_profile(profile_id):
    profile = _fetch_template_profile_by_id(session["user_id"], profile_id)
    if not profile:
        return jsonify({"error": "Template profile not found"}), 404

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM template_profiles WHERE id = ? AND user_id = ?",
        (profile_id, session["user_id"]),
    )
    if profile["is_default"]:
        cur.execute(
            """
            UPDATE template_profiles
            SET is_default = 1, updated_at = CURRENT_TIMESTAMP
            WHERE id = (
                SELECT id
                FROM template_profiles
                WHERE user_id = ? AND note_type = ?
                ORDER BY updated_at DESC, created_at DESC
                LIMIT 1
            )
            """,
            (session["user_id"], profile["note_type"]),
        )
    conn.commit()
    conn.close()
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
    context, error_response, status_code = build_generation_context(payload)

    if error_response:
        return error_response, status_code

    try:
        note_text, generation_meta = two_stage_generate(
            context["shorthand"],
            user_id=session.get("user_id"),
            note_type=context["note_type"],
            template_profile=context.get("template_profile"),
            specialty=context["specialty"],
            template_content=context.get("template_content"),
            retrieved_examples=context.get("retrieved_examples"),
            case_facts=context.get("case_facts"),
        )
    except GenerationLimitError as exc:
        return jsonify({"error": str(exc)}), 429
    except RateLimitError:
        return jsonify({"error": "AI generation is temporarily unavailable. Please try again shortly."}), 503
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": f"Generation failed: {str(exc)}"}), 500

    _log_generated_note(
        session.get("user_id"),
        context["note_type"],
        context["shorthand"],
        note_text,
        context["procedure_label"],
    )

    return jsonify({
        "note": note_text,
        "case_facts": context["case_facts"],
        "procedure_label": context["procedure_label"],
        "note_type": context["note_type"],
        "used_template": bool(context["template_content"]),
        "teaching_signals": context.get("teaching_signals", {}),
        "usage": generation_meta.get("usage", {}),
        "asserted_from_model": generation_meta.get("asserted_from_model", {}),
        "validation": generation_meta.get("validation", {}),
    })


@app.route("/generate-note-stream", methods=["POST"])
@require_user_auth
def generate_note_stream():
    payload = request.get_json(silent=True) or {}
    context, error_response, status_code = build_generation_context(payload)

    if error_response:
        return error_response, status_code

    def generate():
        yield sse_event({
            "type": "meta",
            "case_facts": context["case_facts"],
            "procedure_label": context["procedure_label"],
            "note_type": context["note_type"],
            "used_template": bool(context["template_content"]),
            "teaching_signals": context.get("teaching_signals", {}),
            "timings": context.get("timings", {}),
        })

        try:
            note_text, generation_meta = two_stage_generate(
                context["shorthand"],
                user_id=session.get("user_id"),
                note_type=context["note_type"],
                template_profile=context.get("template_profile"),
                specialty=context["specialty"],
                template_content=context.get("template_content"),
                retrieved_examples=context.get("retrieved_examples"),
                case_facts=context.get("case_facts"),
            )
            _log_generated_note(
                session.get("user_id"),
                context["note_type"],
                context["shorthand"],
                note_text,
                context["procedure_label"],
            )
            yield sse_event({"type": "delta", "delta": note_text})
            yield sse_event({
                "type": "done",
                "timings": context.get("timings", {}),
                "usage": generation_meta.get("usage", {}),
                "asserted_from_model": generation_meta.get("asserted_from_model", {}),
                "validation": generation_meta.get("validation", {}),
            })
        except GenerationLimitError as exc:
            yield sse_event({"type": "error", "error": str(exc)})
        except RateLimitError:
            yield sse_event({"type": "error", "error": "AI generation is temporarily unavailable. Please try again shortly."})
        except ValueError as exc:
            yield sse_event({"type": "error", "error": str(exc)})
        except Exception as exc:
            yield sse_event({"type": "error", "error": f"Generation failed: {str(exc)}"})

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.route("/api/notes/<int:note_id>/finalize", methods=["POST"])
@require_user_auth
def finalize_note(note_id):
    payload = request.get_json(silent=True) or {}
    final_text = (payload.get("final_text") or "").strip()
    phi_merged = bool(payload.get("phi_merged"))

    if not final_text:
        return jsonify({"error": "Final text is required."}), 400
    if not phi_merged:
        return jsonify({"error": "Confirm PHI has been merged locally before finalizing."}), 400

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, editor_notes FROM training_examples WHERE id = ?", (note_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "Note not found."}), 404

    finalized_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    audit_line = f"Finalized by user {session['user_id']} at {finalized_at}"
    cur.execute(
        """
        UPDATE training_examples
        SET corrected_output = ?,
            editor_notes = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (
            final_text,
            _append_editor_note(row["editor_notes"], audit_line),
            note_id,
        ),
    )
    conn.commit()
    conn.close()

    return jsonify({"status": "ok"})


@app.route("/api/feedback", methods=["POST"])
@require_user_auth
def save_feedback():
    payload = request.get_json(silent=True) or {}

    rating = str(payload.get("rating") or "").strip()
    feedback_score = _feedback_score(rating)
    if feedback_score <= 0:
        return jsonify({"error": "Rating must be a whole number from 1 to 10."}), 400

    note_type = (payload.get("note_type") or "consult_note").strip()
    if note_type not in ALLOWED_NOTE_TYPES:
        return jsonify({"error": "Invalid note type."}), 400

    shorthand = (payload.get("shorthand") or "").strip()
    generated_note = (payload.get("generated_note") or "").strip()
    procedure = (payload.get("procedure") or "").strip()
    comment = (payload.get("comment") or "").strip()
    delivery_action = (payload.get("delivery_action") or "copy").strip() or "copy"
    module_key = (
        payload.get("module_key")
        or _infer_feedback_module(note_type, shorthand, generated_note=generated_note, procedure=procedure)
    )
    module_label = _module_label(module_key)

    teaching_signals = payload.get("teaching_signals") or {}
    retrieval_source_summary = teaching_signals.get("retrieval_source_summary") or {}
    if not isinstance(retrieval_source_summary, dict):
        retrieval_source_summary = {}

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id
        FROM feedback
        WHERE user_id = ?
          AND note_type = ?
          AND shorthand = ?
          AND generated_note = ?
        LIMIT 1
        """,
        (
            session.get("user_id"),
            note_type,
            shorthand,
            generated_note,
        ),
    )
    existing_feedback = cur.fetchone()
    if existing_feedback:
        conn.close()
        return jsonify({"error": "This note has already been scored."}), 409

    cur.execute(
        """
        INSERT INTO feedback (
            user_id, shorthand, procedure, rating, comment, generated_note, note_type,
            delivery_action, module_key, module_label, feedback_score, template_profile_name,
            strict_used, style_used, exact_block_count, exact_used_count, retrieved_example_count,
            retrieval_source_summary
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session.get("user_id"),
            shorthand,
            procedure,
            rating,
            comment,
            generated_note,
            note_type,
            delivery_action,
            module_key,
            module_label,
            feedback_score,
            teaching_signals.get("template_profile_name"),
            1 if teaching_signals.get("strict_used") else 0,
            1 if teaching_signals.get("style_used") else 0,
            int(teaching_signals.get("exact_block_count") or 0),
            int(payload.get("exact_used_count") or teaching_signals.get("exact_used_count") or 0),
            int(teaching_signals.get("retrieved_example_count") or 0),
            json.dumps(retrieval_source_summary),
        )
    )
    conn.commit()
    conn.close()

    if module_key:
        refresh_conn = get_conn()
        try:
            _refresh_curriculum_pressure(refresh_conn, module_key)
            refresh_conn.commit()
        finally:
            refresh_conn.close()

    return jsonify({"status": "ok"})

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


@app.route("/admin/scenarios")
@require_admin_auth
def scenario_hub():
    specialty_filter = ACTIVE_CURRICULUM_SPECIALTY
    module_filter = _normalize_module_key(request.args.get("module"))
    note_type_filter = (request.args.get("note_type") or "").strip()
    level_filter = (request.args.get("level") or "").strip()

    ensure_default_scenarios(
        specialty_filter=specialty_filter,
        note_type_filter=note_type_filter or None,
    )

    conn = get_conn()
    cur = conn.cursor()
    daily_result = {
        "rows": _daily_urgent_scenarios(cur, limit=5),
        "created": 0,
        "batch_date": _scenario_batch_date(),
        "error": None,
    }
    if not daily_result["rows"]:
        daily_result = _generate_daily_urgent_scenarios(conn, cur, limit=5)
    generated_error = request.args.get("generate_error") or daily_result.get("error")

    scenarios = daily_result["rows"]
    if module_filter:
        scenarios = [row for row in scenarios if row.get("module_key") == module_filter]
    if note_type_filter:
        scenarios = [row for row in scenarios if row.get("note_type") == note_type_filter]
    if level_filter.isdigit():
        scenarios = [row for row in scenarios if int(row.get("next_target_level") or 0) == int(level_filter)]

    cur.execute(
        """
        SELECT module_key,
               COUNT(*) AS scenario_count,
               ROUND(AVG(model_confidence), 3) AS avg_confidence,
               ROUND(AVG(curriculum_pressure), 3) AS avg_pressure,
               COALESCE(SUM(review_count), 0) AS total_reviews,
               SUM(CASE WHEN next_target_level = 1 THEN 1 ELSE 0 END) AS level1_queue,
               SUM(CASE WHEN next_target_level = 2 THEN 1 ELSE 0 END) AS level2_queue,
               SUM(CASE WHEN next_target_level = 3 THEN 1 ELSE 0 END) AS level3_queue
        FROM scenario_templates
        WHERE specialty = ?
        GROUP BY module_key
        """,
        (specialty_filter,)
    )
    module_metrics = {row["module_key"]: row for row in cur.fetchall()}
    module_rows = []
    for module in _curriculum_modules():
        row = module_metrics.get(module["key"])
        module_rows.append({
            "key": module["key"],
            "label": module["label"],
            "rank": module["rank"],
            "note_type": module["note_type"],
            "description": module["description"],
            "scenario_count": row["scenario_count"] if row else 0,
            "avg_confidence": row["avg_confidence"] if row else 0,
            "avg_pressure": row["avg_pressure"] if row else 0,
            "total_reviews": row["total_reviews"] if row else 0,
            "level1_queue": row["level1_queue"] if row else 0,
            "level2_queue": row["level2_queue"] if row else 0,
            "level3_queue": row["level3_queue"] if row else 0,
        })

    cur.execute(
        """
        SELECT COUNT(*) AS scenario_count,
               COALESCE(SUM(review_count), 0) AS total_reviews,
               ROUND(AVG(model_confidence), 3) AS avg_confidence,
               SUM(CASE WHEN next_target_level = 1 THEN 1 ELSE 0 END) AS level1_queue
        FROM scenario_templates
        WHERE specialty = ?
        """,
        (specialty_filter,)
    )
    summary = cur.fetchone()

    conn.close()

    return render_template(
        "scenario_hub.html",
        scenarios=scenarios,
        module_rows=module_rows,
        summary=summary,
        generated_error=generated_error,
        scenario_batch_date=daily_result.get("batch_date"),
        selected_specialty=specialty_filter,
        selected_module=module_filter,
        selected_note_type=note_type_filter,
        selected_level=level_filter,
        curriculum_modules=_curriculum_modules(),
    )


@app.route("/admin/scenarios/refresh-urgent", methods=["POST"])
@require_admin_auth
def refresh_urgent_scenarios():
    specialty = ACTIVE_CURRICULUM_SPECIALTY
    ensure_default_scenarios(specialty_filter=specialty)

    conn = get_conn()
    cur = conn.cursor()
    result = _generate_daily_urgent_scenarios(conn, cur, limit=5, force=True)
    conn.close()
    if result.get("error"):
        return redirect(url_for("scenario_hub", generate_error=result["error"]))
    return redirect(url_for("scenario_hub", generated=result.get("created") or 0))


@app.route("/admin/scenarios/seed", methods=["POST"])
@require_admin_auth
def seed_scenarios():
    specialty = ACTIVE_CURRICULUM_SPECIALTY
    note_type = (request.form.get("note_type") or "").strip()
    sync_result = ensure_default_scenarios(
        specialty_filter=specialty,
        note_type_filter=note_type or None,
    )
    return redirect(url_for(
        "scenario_hub",
        module=_normalize_module_key(request.form.get("module")) or None,
        note_type=note_type or None,
        seeded=sync_result["created"],
        refreshed=sync_result["updated"],
    ))


@app.route("/admin/scenarios/generate", methods=["POST"])
@require_admin_auth
def generate_scenarios():
    specialty = ACTIVE_CURRICULUM_SPECIALTY
    note_type = (request.form.get("note_type") or "consult_note").strip()
    module_key = _normalize_module_key(request.form.get("module_key"))
    focus = (request.form.get("focus") or "").strip()

    try:
        target_level = int(request.form.get("target_level") or 1)
    except ValueError:
        target_level = 1

    try:
        count = int(request.form.get("count") or 3)
    except ValueError:
        count = 3

    target_level = max(1, min(target_level, 3))
    count = max(1, min(count, 6))

    module = GENERAL_SURGERY_MODULE_MAP.get(module_key or "")
    if not module:
        return redirect(url_for(
            "scenario_hub",
            note_type=note_type,
            level=str(target_level),
            generate_error="Choose a module before generating scenarios.",
        ))
    note_type = module["note_type"]

    if not os.getenv("OPENAI_API_KEY"):
        return redirect(url_for(
            "scenario_hub",
            module=module_key,
            note_type=note_type,
            level=str(target_level),
            generate_error="Missing OPENAI_API_KEY environment variable.",
        ))

    conn = get_conn()
    cur = conn.cursor()
    existing_titles = _existing_scenario_titles(cur, specialty=specialty, note_type=note_type, module_key=module_key)
    prompt = build_scenario_generation_prompt(
        specialty=specialty,
        note_type=note_type,
        module_label=module["label"],
        module_description=module["description"],
        target_level=target_level,
        count=count,
        focus=focus,
        existing_titles=existing_titles,
    )

    try:
        raw_text, _ = call_model_and_log(
            prompt,
            user_id=session.get("user_id"),
            model=DEFAULT_MODEL_NAME,
            temperature=0.0,
            max_output_tokens=1800,
        )
        scenarios = _parse_json_array_output(raw_text)

        created = 0
        title_pool = {title.lower().strip() for title in existing_titles}
        for idx, item in enumerate(scenarios, start=1):
            if not isinstance(item, dict):
                continue

            title = (item.get("title") or "").strip()
            scenario_brief = (item.get("scenario_brief") or "").strip()
            if not title or not scenario_brief:
                continue

            base_title = title
            suffix = 2
            while title.lower() in title_pool:
                title = f"{base_title} ({suffix})"
                suffix += 1
            title_pool.add(title.lower())

            scenario_payload = {
                "specialty": specialty,
                "note_type": note_type,
                "module_key": module_key,
                "module_label": module["label"],
                "module_rank": module["rank"],
                "title": title,
                "diagnosis": (item.get("diagnosis") or "").strip() or None,
                "procedure_focus": (item.get("procedure_focus") or "").strip() or None,
                "complexity_level": max(1, min(int(item.get("complexity_level") or target_level), 3)),
                "scenario_brief": scenario_brief,
                "learning_objectives": (item.get("learning_objectives") or "").strip() or None,
                "generated_by": "ai-scenario-generator",
                "focus": focus,
                "question_prompt": (item.get("question_prompt") or "").strip() or None,
                "why_now": (item.get("why_now") or "").strip() or None,
            }
            _insert_scenario_template(cur, scenario_payload)
            created += 1

        conn.commit()
    except RateLimitError:
        conn.close()
        return redirect(url_for(
            "scenario_hub",
            module=module_key,
            note_type=note_type,
            level=str(target_level),
            generate_error="AI scenario generation is temporarily unavailable.",
        ))
    except Exception as exc:
        conn.close()
        return redirect(url_for(
            "scenario_hub",
            module=module_key,
            note_type=note_type,
            level=str(target_level),
            generate_error=f"Unable to generate scenarios: {str(exc)}",
        ))

    conn.close()
    return redirect(url_for(
        "scenario_hub",
        module=module_key,
        note_type=note_type,
        level=str(target_level),
        generated=created,
    ))


@app.route("/admin/scenarios/<int:scenario_id>/review", methods=["GET", "POST"])
@require_admin_auth
def review_scenario(scenario_id):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT *
        FROM scenario_templates
        WHERE id = ?
        """,
        (scenario_id,)
    )
    scenario = cur.fetchone()
    scenario_map = dict(scenario) if scenario else None

    if not scenario:
        conn.close()
        return redirect(url_for("scenario_hub"))

    error = None
    if request.method == "POST":
        reviewer_name = (request.form.get("reviewer_name") or "").strip()
        reviewer_role = (request.form.get("reviewer_role") or "").strip()
        shorthand_input = (request.form.get("shorthand_input") or "").strip()
        generated_draft = (request.form.get("generated_draft") or "").strip()
        corrected_output = (request.form.get("corrected_output") or "").strip()
        reviewer_comments = (request.form.get("reviewer_comments") or "").strip()
        issue_tags = (request.form.get("issue_tags") or "").strip()
        quality_status = (request.form.get("quality_status") or "approved").strip()
        grade_level = (request.form.get("grade_level") or "level_1_pass").strip()

        if quality_status not in TRAINING_STATUSES:
            quality_status = "approved"
        if grade_level not in SCENARIO_GRADE_LEVELS:
            grade_level = "level_1_pass"

        if not shorthand_input or not corrected_output:
            error = "Shorthand input and corrected output are required."
        else:
            interpreted = _interpret_review_feedback(
                generated_draft=generated_draft,
                corrected_output=corrected_output,
                reviewer_comments=reviewer_comments,
            )

            merged_tags = []
            seen_tags = set()
            for raw_tag in (issue_tags.split(",") if issue_tags else []):
                cleaned = raw_tag.strip()
                if cleaned and cleaned not in seen_tags:
                    merged_tags.append(cleaned)
                    seen_tags.add(cleaned)
            for derived_tag in interpreted["issue_tags"]:
                if derived_tag not in seen_tags:
                    merged_tags.append(derived_tag)
                    seen_tags.add(derived_tag)

            review_score = round(
                (
                    0.6 * _grade_to_score(grade_level)
                    + 0.4 * (1.0 if quality_status in {"approved", "gold"} else 0.35)
                ),
                4,
            )

            cur.execute(
                """
                INSERT INTO scenario_reviews (
                    scenario_template_id, specialty, note_type, reviewer_name, reviewer_role,
                    shorthand_input, generated_draft, corrected_output, reviewer_comments,
                    interpreted_feedback_json, interpreted_lessons, issue_tags,
                    quality_status, grade_level, review_score, edit_similarity
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    scenario_id,
                    scenario_map["specialty"],
                    scenario_map["note_type"],
                    reviewer_name,
                    reviewer_role,
                    shorthand_input,
                    generated_draft,
                    corrected_output,
                    reviewer_comments,
                    json.dumps(interpreted, ensure_ascii=True),
                    "\n".join(interpreted["lessons"]),
                    ", ".join(merged_tags),
                    quality_status,
                    grade_level,
                    review_score,
                    interpreted["edit_similarity"],
                )
            )
            review_id = cur.lastrowid

            created_training_example_id = None
            if quality_status in {"approved", "gold"}:
                created_training_example_id = _promote_review_to_training_example(
                    cur,
                    scenario_map,
                    review_id,
                    {
                        "shorthand_input": shorthand_input,
                        "generated_draft": generated_draft,
                        "corrected_output": corrected_output,
                        "quality_status": quality_status,
                        "issue_tags": ", ".join(merged_tags),
                        "reviewer_comments": reviewer_comments,
                        "interpreted_lessons": "\n".join(interpreted["lessons"]),
                        "submitted_by_trainer_id": None,
                    },
                    reviewer_name or "scenario-reviewer",
                )

            _refresh_scenario_metrics(conn, scenario_id)
            conn.commit()
            conn.close()
            return redirect(url_for("review_scenario", scenario_id=scenario_id, saved=1))

    cur.execute(
        """
        SELECT id, reviewer_name, reviewer_role, shorthand_input, generated_draft, corrected_output,
               reviewer_comments, interpreted_lessons, issue_tags, quality_status, grade_level,
               review_score, edit_similarity, created_at
        FROM scenario_reviews
        WHERE scenario_template_id = ?
        ORDER BY created_at DESC
        LIMIT 8
        """,
        (scenario_id,)
    )
    recent_reviews = cur.fetchall()
    conn.close()

    return render_template(
        "review_scenario.html",
        scenario=_prepare_scenario_for_display(scenario_map),
        recent_reviews=recent_reviews,
        training_statuses=TRAINING_STATUSES,
        scenario_grade_levels=SCENARIO_GRADE_LEVELS,
        error=error,
        saved=request.args.get("saved"),
    )


@app.route("/admin/training-library")
@require_admin_auth
def training_library():
    specialty_filter = (request.args.get("specialty") or "").strip()
    note_type_filter = (request.args.get("note_type") or "").strip()
    status_filter = (request.args.get("status") or "").strip()

    conn = get_conn()
    cur = conn.cursor()

    query = """
        SELECT id, specialty, note_type, title, shorthand_input, generated_draft, corrected_output,
               status, issue_tags, editor_notes, created_by, created_at, updated_at, source_kind, in_master_canon
        FROM training_examples
        WHERE (COALESCE(in_master_canon, 0) = 1 OR status IN ('approved', 'gold'))
    """
    params = []

    if specialty_filter:
        query += " AND specialty = ?"
        params.append(specialty_filter)
    if note_type_filter:
        query += " AND note_type = ?"
        params.append(note_type_filter)
    if status_filter:
        query += " AND status = ?"
        params.append(status_filter)

    query += " ORDER BY COALESCE(in_master_canon, 0) DESC, updated_at DESC, created_at DESC"
    cur.execute(query, params)
    rows = []
    for row in cur.fetchall():
        item = dict(row)
        item["source_label"] = _source_kind_label(item.get("source_kind"))
        rows.append(item)

    cur.execute("""
        SELECT DISTINCT specialty
        FROM training_examples
        WHERE specialty IS NOT NULL AND specialty != ''
        ORDER BY specialty ASC
    """)
    specialties = cur.fetchall()

    conn.close()

    return render_template(
        "training_library.html",
        training_examples=rows,
        specialties=specialties,
        selected_specialty=specialty_filter,
        selected_note_type=note_type_filter,
        selected_status=status_filter,
        note_types=sorted(ALLOWED_NOTE_TYPES),
        training_statuses=TRAINING_STATUSES,
    )


@app.route("/admin/training-library/<int:example_id>/edit", methods=["GET", "POST"])
@require_admin_auth
def edit_training_example(example_id):
    conn = get_conn()
    cur = conn.cursor()

    if request.method == "POST":
        specialty = (request.form.get("specialty") or "").strip()
        note_type = (request.form.get("note_type") or "").strip()
        title = (request.form.get("title") or "").strip()
        shorthand_input = (request.form.get("shorthand_input") or "").strip()
        generated_draft = (request.form.get("generated_draft") or "").strip()
        corrected_output = (request.form.get("corrected_output") or "").strip()
        status = (request.form.get("status") or "approved").strip()
        issue_tags = (request.form.get("issue_tags") or "").strip()
        editor_notes = (request.form.get("editor_notes") or "").strip()

        if note_type not in ALLOWED_NOTE_TYPES:
            note_type = "consult_note"
        if status not in TRAINING_STATUSES:
            status = "approved"

        if not specialty or not shorthand_input or not corrected_output:
            cur.execute("""
                SELECT *
                FROM training_examples
                WHERE id = ?
            """, (example_id,))
            row = cur.fetchone()
            conn.close()
            return render_template(
                "edit_training_example.html",
                example=row,
                specialty_options=SPECIALTY_OPTIONS,
                training_statuses=TRAINING_STATUSES,
                error="Specialty, shorthand input, and corrected output are required."
            )

        cur.execute("""
            UPDATE training_examples
            SET specialty = ?, note_type = ?, title = ?, shorthand_input = ?, generated_draft = ?,
                corrected_output = ?, status = ?, issue_tags = ?, editor_notes = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (
            specialty, note_type, title, shorthand_input, generated_draft,
            corrected_output, status, issue_tags, editor_notes, example_id
        ))
        conn.commit()
        conn.close()
        return redirect(url_for("training_library"))

    cur.execute("""
        SELECT *
        FROM training_examples
        WHERE id = ?
    """, (example_id,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return redirect(url_for("training_library"))

    return render_template(
        "edit_training_example.html",
        example=row,
        specialty_options=SPECIALTY_OPTIONS,
        training_statuses=TRAINING_STATUSES,
        error=None
    )


@app.route("/admin/training-library/<int:example_id>/delete", methods=["POST"])
@require_admin_auth
def delete_training_example(example_id):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM training_examples WHERE id = ?", (example_id,))
        row = cur.fetchone()
        if not row:
            conn.close()
            return redirect(url_for("training_library"))

        cur.execute(
            """
            UPDATE scenario_reviews
            SET created_training_example_id = NULL, updated_at = CURRENT_TIMESTAMP
            WHERE created_training_example_id = ?
            """,
            (example_id,),
        )
        cur.execute(
            """
            UPDATE expert_requests
            SET created_training_example_id = NULL, updated_at = CURRENT_TIMESTAMP
            WHERE created_training_example_id = ?
            """,
            (example_id,),
        )
        cur.execute(
            """
            UPDATE model_usage
            SET training_example_id = NULL
            WHERE training_example_id = ?
            """,
            (example_id,),
        )
        cur.execute("DELETE FROM training_examples WHERE id = ?", (example_id,))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.rollback()
        conn.close()
        return redirect(url_for("training_library", error="Unable to delete canon note because it is still linked elsewhere."))
    except sqlite3.OperationalError:
        conn.rollback()
        conn.close()
        return redirect(url_for("training_library", error="Unable to delete canon note right now because the database is busy."))
    conn.close()
    return redirect(url_for("training_library", deleted=1))


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


@app.route("/admin/generate-training-draft", methods=["POST"])
@require_admin_auth
def generate_training_draft():
    payload = request.get_json(silent=True) or {}
    context, error_response, status_code = build_generation_context(payload, use_user_template=False)

    if error_response:
        return error_response, status_code

    try:
        note_text, generation_meta = two_stage_generate(
            context["shorthand"],
            user_id=session.get("user_id"),
            note_type=context["note_type"],
            template_profile=context.get("template_profile"),
            training_example_id=payload.get("training_example_id"),
            specialty=context["specialty"],
            template_content=context.get("template_content"),
            retrieved_examples=context.get("retrieved_examples"),
            case_facts=context.get("case_facts"),
        )
    except GenerationLimitError as exc:
        return jsonify({"error": str(exc)}), 429
    except RateLimitError:
        return jsonify({"error": "AI generation is temporarily unavailable. Please try again shortly."}), 503
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": f"Generation failed: {str(exc)}"}), 500

    return jsonify({
        "note": note_text,
        "case_facts": context["case_facts"],
        "procedure_label": context["procedure_label"],
        "note_type": context["note_type"],
        "usage": generation_meta.get("usage", {}),
        "asserted_from_model": generation_meta.get("asserted_from_model", {}),
        "validation": generation_meta.get("validation", {}),
        "timings": context.get("timings", {}),
    })


@app.route("/admin/save-training-example", methods=["POST"])
@require_admin_auth
def save_training_example():
    payload = request.get_json(silent=True) or {}

    specialty = (payload.get("specialty") or "").strip()
    note_type = (payload.get("note_type") or "consult_note").strip()
    title = (payload.get("title") or "").strip()
    shorthand_input = (payload.get("shorthand_input") or "").strip()
    generated_draft = (payload.get("generated_draft") or "").strip()
    corrected_output = (payload.get("corrected_output") or "").strip()
    status = (payload.get("status") or "approved").strip()
    issue_tags = payload.get("issue_tags", [])
    editor_notes = (payload.get("editor_notes") or "").strip()
    accepted_assumptions_json = (payload.get("accepted_assumptions_json") or "[]").strip() or "[]"
    module_key = _normalize_module_key(payload.get("module_key"))
    module_label = GENERAL_SURGERY_MODULE_MAP.get(module_key, {}).get("label") if module_key else None

    if note_type not in ALLOWED_NOTE_TYPES:
        return jsonify({"error": "Invalid note type"}), 400
    if status not in TRAINING_STATUSES:
        return jsonify({"error": "Invalid training status"}), 400
    if not specialty or not shorthand_input or not corrected_output:
        return jsonify({"error": "Specialty, shorthand input, and corrected output are required"}), 400

    issue_tags_str = ", ".join(issue_tags) if isinstance(issue_tags, list) else str(issue_tags or "")

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO training_examples (
            specialty, note_type, title, shorthand_input, generated_draft, corrected_output,
            status, issue_tags, editor_notes, created_by, module_key, module_label, accepted_assumptions_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            specialty,
            note_type,
            title,
            shorthand_input,
            generated_draft,
            corrected_output,
            status,
            issue_tags_str,
            editor_notes,
            "admin-team",
            module_key or None,
            module_label,
            accepted_assumptions_json,
        )
    )
    created_id = cur.lastrowid
    if payload.get("in_master_canon"):
        cur.execute("UPDATE training_examples SET in_master_canon = 1 WHERE id = ?", (created_id,))
    conn.commit()
    conn.close()

    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(debug=True, port=5001)
