import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "surginote.db"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def ensure_column(cur, table_name, column_name, column_sql):
    cur.execute(f"PRAGMA table_info({table_name})")
    columns = [row["name"] for row in cur.fetchall()]
    if column_name not in columns:
        cur.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_sql}")


def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS access_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT NOT NULL UNIQUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE,
        password_hash TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    ensure_column(cur, "users", "phone", "phone TEXT")
    ensure_column(cur, "users", "is_admin", "is_admin INTEGER NOT NULL DEFAULT 0")
    ensure_column(cur, "users", "is_expert", "is_expert INTEGER NOT NULL DEFAULT 0")
    ensure_column(cur, "users", "first_name", "first_name TEXT")
    ensure_column(cur, "users", "last_name", "last_name TEXT")
    ensure_column(cur, "users", "credential_title", "credential_title TEXT")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS user_preferences (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        preference_key TEXT NOT NULL,
        preference_value TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        shorthand TEXT,
        procedure TEXT,
        rating TEXT,
        comment TEXT,
        generated_note TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    ensure_column(cur, "feedback", "note_type", "note_type TEXT")
    ensure_column(cur, "feedback", "delivery_action", "delivery_action TEXT")
    ensure_column(cur, "feedback", "module_key", "module_key TEXT")
    ensure_column(cur, "feedback", "module_label", "module_label TEXT")
    ensure_column(cur, "feedback", "feedback_score", "feedback_score REAL")
    ensure_column(cur, "feedback", "user_id", "user_id INTEGER")
    ensure_column(cur, "feedback", "template_profile_name", "template_profile_name TEXT")
    ensure_column(cur, "feedback", "strict_used", "strict_used INTEGER NOT NULL DEFAULT 0")
    ensure_column(cur, "feedback", "style_used", "style_used INTEGER NOT NULL DEFAULT 0")
    ensure_column(cur, "feedback", "exact_block_count", "exact_block_count INTEGER NOT NULL DEFAULT 0")
    ensure_column(cur, "feedback", "exact_used_count", "exact_used_count INTEGER NOT NULL DEFAULT 0")
    ensure_column(cur, "feedback", "retrieved_example_count", "retrieved_example_count INTEGER NOT NULL DEFAULT 0")
    ensure_column(cur, "feedback", "retrieval_source_summary", "retrieval_source_summary TEXT")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS procedure_samples (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        procedure TEXT NOT NULL,
        title TEXT,
        shorthand_input TEXT NOT NULL,
        ideal_note TEXT NOT NULL,
        tags TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS templates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        note_type TEXT NOT NULL,
        content TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, note_type),
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS template_profiles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        note_type TEXT NOT NULL,
        name TEXT NOT NULL,
        strict_template_text TEXT,
        strict_enabled INTEGER NOT NULL DEFAULT 1,
        style_example_text TEXT,
        style_enabled INTEGER NOT NULL DEFAULT 1,
        is_default INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    """)

    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_template_profiles_user_note_type
    ON template_profiles (user_id, note_type, is_default DESC, updated_at DESC)
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS otp_codes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        phone TEXT NOT NULL,
        code TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        verified INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS training_examples (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        specialty TEXT NOT NULL,
        note_type TEXT NOT NULL,
        title TEXT,
        shorthand_input TEXT NOT NULL,
        generated_draft TEXT,
        corrected_output TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'approved',
        issue_tags TEXT,
        editor_notes TEXT,
        created_by TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    ensure_column(cur, "training_examples", "scenario_template_id", "scenario_template_id INTEGER")
    ensure_column(cur, "training_examples", "scenario_review_id", "scenario_review_id INTEGER")
    ensure_column(cur, "training_examples", "source_kind", "source_kind TEXT DEFAULT 'manual'")
    ensure_column(cur, "training_examples", "module_key", "module_key TEXT")
    ensure_column(cur, "training_examples", "module_label", "module_label TEXT")
    ensure_column(cur, "training_examples", "accepted_assumptions_json", "accepted_assumptions_json TEXT")

    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_training_examples_specialty_note_type
    ON training_examples (specialty, note_type, status, created_at DESC)
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS scenario_templates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        specialty TEXT NOT NULL,
        note_type TEXT NOT NULL,
        title TEXT NOT NULL,
        module_key TEXT,
        module_label TEXT,
        module_rank INTEGER,
        diagnosis TEXT,
        procedure_focus TEXT,
        complexity_level INTEGER NOT NULL DEFAULT 1,
        scenario_status TEXT NOT NULL DEFAULT 'available',
        scenario_brief TEXT NOT NULL,
        learning_objectives TEXT,
        structured_facts_json TEXT,
        generated_by TEXT,
        model_confidence REAL NOT NULL DEFAULT 0,
        review_count INTEGER NOT NULL DEFAULT 0,
        approved_count INTEGER NOT NULL DEFAULT 0,
        gold_count INTEGER NOT NULL DEFAULT 0,
        average_edit_similarity REAL NOT NULL DEFAULT 0,
        next_target_level INTEGER NOT NULL DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_scenario_templates_specialty_note_type
    ON scenario_templates (specialty, note_type, complexity_level, model_confidence)
    """)

    ensure_column(cur, "scenario_templates", "module_key", "module_key TEXT")
    ensure_column(cur, "scenario_templates", "module_label", "module_label TEXT")
    ensure_column(cur, "scenario_templates", "module_rank", "module_rank INTEGER")
    ensure_column(cur, "scenario_templates", "user_feedback_score", "user_feedback_score REAL NOT NULL DEFAULT 0")
    ensure_column(cur, "scenario_templates", "user_feedback_count", "user_feedback_count INTEGER NOT NULL DEFAULT 0")
    ensure_column(cur, "scenario_templates", "curriculum_pressure", "curriculum_pressure REAL NOT NULL DEFAULT 0")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS scenario_reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scenario_template_id INTEGER NOT NULL,
        specialty TEXT NOT NULL,
        note_type TEXT NOT NULL,
        reviewer_name TEXT,
        reviewer_role TEXT,
        shorthand_input TEXT NOT NULL,
        generated_draft TEXT,
        corrected_output TEXT NOT NULL,
        reviewer_comments TEXT,
        interpreted_feedback_json TEXT,
        interpreted_lessons TEXT,
        issue_tags TEXT,
        quality_status TEXT NOT NULL DEFAULT 'approved',
        grade_level TEXT NOT NULL DEFAULT 'level_1_pass',
        review_score REAL NOT NULL DEFAULT 0,
        edit_similarity REAL NOT NULL DEFAULT 0,
        created_training_example_id INTEGER,
        submitted_by_trainer_id INTEGER,
        submission_status TEXT NOT NULL DEFAULT 'approved',
        admin_review_notes TEXT,
        reviewed_by_admin_id INTEGER,
        reviewed_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (scenario_template_id) REFERENCES scenario_templates(id) ON DELETE CASCADE,
        FOREIGN KEY (created_training_example_id) REFERENCES training_examples(id) ON DELETE SET NULL
    )
    """)
    ensure_column(cur, "scenario_reviews", "submitted_by_trainer_id", "submitted_by_trainer_id INTEGER")
    ensure_column(cur, "scenario_reviews", "submission_status", "submission_status TEXT NOT NULL DEFAULT 'approved'")
    ensure_column(cur, "scenario_reviews", "admin_review_notes", "admin_review_notes TEXT")
    ensure_column(cur, "scenario_reviews", "reviewed_by_admin_id", "reviewed_by_admin_id INTEGER")
    ensure_column(cur, "scenario_reviews", "reviewed_at", "reviewed_at TIMESTAMP")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS trainers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        email TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        is_active INTEGER NOT NULL DEFAULT 1,
        send_interval_days INTEGER NOT NULL DEFAULT 7,
        preferred_module_key TEXT,
        last_case_sent_at TIMESTAMP,
        last_login_at TIMESTAMP,
        reset_token TEXT,
        reset_token_expires_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS trainer_case_assignments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        trainer_id INTEGER NOT NULL,
        scenario_template_id INTEGER NOT NULL,
        scenario_review_id INTEGER,
        assignment_status TEXT NOT NULL DEFAULT 'assigned',
        delivery_source TEXT NOT NULL DEFAULT 'scheduled_email',
        email_sent_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (trainer_id) REFERENCES trainers(id) ON DELETE CASCADE,
        FOREIGN KEY (scenario_template_id) REFERENCES scenario_templates(id) ON DELETE CASCADE,
        FOREIGN KEY (scenario_review_id) REFERENCES scenario_reviews(id) ON DELETE SET NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS expert_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        expert_user_id INTEGER NOT NULL,
        requested_by_admin_id INTEGER,
        request_kind TEXT NOT NULL DEFAULT 'gold_standard_note',
        title TEXT NOT NULL,
        note_type TEXT NOT NULL,
        module_key TEXT,
        module_label TEXT,
        scenario_template_id INTEGER,
        request_brief TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        shorthand_input TEXT,
        generated_draft TEXT,
        corrected_output TEXT,
        expert_notes TEXT,
        created_training_example_id INTEGER,
        submitted_at TIMESTAMP,
        completed_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (expert_user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (scenario_template_id) REFERENCES scenario_templates(id) ON DELETE SET NULL,
        FOREIGN KEY (created_training_example_id) REFERENCES training_examples(id) ON DELETE SET NULL
    )
    """)
    ensure_column(cur, "expert_requests", "accepted_assumptions_json", "accepted_assumptions_json TEXT")

    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_scenario_reviews_template_status
    ON scenario_reviews (scenario_template_id, quality_status, grade_level, created_at DESC)
    """)

    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_scenario_reviews_specialty_note_type
    ON scenario_reviews (specialty, note_type, quality_status, created_at DESC)
    """)

    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_feedback_module_created
    ON feedback (module_key, created_at DESC)
    """)

    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_trainers_active_email
    ON trainers (is_active, email)
    """)

    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_trainer_case_assignments_trainer_status
    ON trainer_case_assignments (trainer_id, assignment_status, created_at DESC)
    """)

    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_templates_user_note_type
    ON templates (user_id, note_type)
    """)

    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_expert_requests_user_status
    ON expert_requests (expert_user_id, status, created_at DESC)
    """)

    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_expert_requests_status_created
    ON expert_requests (status, created_at DESC)
    """)

    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_otp_codes_phone_created_at
    ON otp_codes (phone, created_at DESC)
    """)

    conn.commit()
    conn.close()
