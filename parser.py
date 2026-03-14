import re

ABBREVIATIONS = {
    "lap chole": "laparoscopic cholecystectomy",
    "robotic chole": "robotic cholecystectomy",
    "rob chole": "robotic cholecystectomy",
    "s/p": "status post",
    "w/": "with",
    "w/o": "without",
    "wnl": "within normal limits",
    "lap": "laparoscopic",
    "rob": "robotic",
    "rih": "right inguinal hernia",
    "lih": "left inguinal hernia",
    "bih": "bilateral inguinal hernia",
    "ebl": "estimated blood loss",
    "uncomp": "uncomplicated",
    "loa": "lysis of adhesions",
    "mesh": "mesh",
    "tapp": "transabdominal preperitoneal",
    "tep": "totally extraperitoneal",
}

PROCEDURE_KEYWORDS = {
    "laparoscopic_cholecystectomy": [
        "laparoscopic cholecystectomy",
    ],
    "robotic_cholecystectomy": [
        "robotic cholecystectomy",
    ],
    "open_inguinal_hernia_repair": [
        "open inguinal hernia repair",
        "open right inguinal hernia repair",
        "open left inguinal hernia repair",
        "right inguinal hernia open repair",
        "left inguinal hernia open repair",
    ],
    "robotic_inguinal_hernia_repair": [
        "robotic inguinal hernia repair",
        "robotic transabdominal preperitoneal",
        "robotic totally extraperitoneal",
        "robotic bilateral inguinal hernia",
    ],
    "open_ventral_hernia_repair": [
        "open ventral hernia repair",
        "open umbilical hernia repair",
        "open incisional hernia repair",
        "ventral hernia",
        "umbilical hernia",
    ],
}

DEFAULTS = {
    "laparoscopic_cholecystectomy": {
        "ebl": "minimal",
        "drain": "none",
        "specimen": "gallbladder",
        "complications": "none",
        "critical_view": True,
    },
    "robotic_cholecystectomy": {
        "ebl": "minimal",
        "drain": "none",
        "specimen": "gallbladder",
        "complications": "none",
        "critical_view": True,
    },
    "open_inguinal_hernia_repair": {
        "ebl": "minimal",
        "drain": "none",
        "mesh_used": True,
        "complications": "none",
    },
    "robotic_inguinal_hernia_repair": {
        "ebl": "minimal",
        "drain": "none",
        "mesh_used": True,
        "complications": "none",
    },
    "open_ventral_hernia_repair": {
        "ebl": "minimal",
        "drain": "none",
        "mesh_used": True,
        "complications": "none",
    },
}


def normalize_text(text: str) -> str:
    t = text.strip().lower()

    for k in sorted(ABBREVIATIONS.keys(), key=len, reverse=True):
        t = re.sub(rf'\b{re.escape(k)}\b', ABBREVIATIONS[k], t)

    t = re.sub(r'(\d{1,3})\s*yo\s*f\b', r'\1 year old female', t, flags=re.IGNORECASE)
    t = re.sub(r'(\d{1,3})\s*yo\s*m\b', r'\1 year old male', t, flags=re.IGNORECASE)

    t = re.sub(r'[.;,]+', ' ', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def extract_demographics(text: str):
    m = re.search(r'(\d{1,3})\s+year old\s+(female|male)', text)
    if not m:
        return {}
    return {"age": int(m.group(1)), "sex": m.group(2)}


def extract_ports(text: str):
    m = re.search(r'(\d+)\s+ports?\b', text)
    return int(m.group(1)) if m else None


def extract_laterality(text: str):
    if "bilateral inguinal hernia" in text:
        return "bilateral"
    if "right inguinal hernia" in text:
        return "right"
    if "left inguinal hernia" in text:
        return "left"
    return None


def extract_defect_type(text: str):
    if "direct defect" in text:
        return "direct"
    if "indirect defect" in text:
        return "indirect"
    return None


def classify_procedure(text: str):
    scores = {}
    for proc, keywords in PROCEDURE_KEYWORDS.items():
        scores[proc] = sum(1 for kw in keywords if kw in text)

    best_proc = max(scores, key=scores.get)
    best_score = scores[best_proc]
    if best_score == 0:
        return None, 0.0

    total = sum(scores.values()) or 1
    return best_proc, round(best_score / total, 2)


def build_case_facts(raw_input: str):
    normalized = normalize_text(raw_input)
    demographics = extract_demographics(normalized)
    procedure, confidence = classify_procedure(normalized)
    ports = extract_ports(normalized)
    laterality = extract_laterality(normalized)
    defect_type = extract_defect_type(normalized)

    operative_details = {}
    if ports:
        operative_details["ports"] = ports
    if laterality:
        operative_details["laterality"] = laterality
    if defect_type:
        operative_details["defect_type"] = defect_type
    if "uncomplicated" in normalized or "no complications" in normalized:
        operative_details["complexity"] = "uncomplicated"
    if "mesh" in normalized:
        operative_details["mesh_mentioned"] = True

    assumptions = DEFAULTS.get(procedure, {}).copy()
    needs_review = []

    if procedure is None:
        needs_review.append("Procedure unclear")

    if procedure in ["open_inguinal_hernia_repair", "robotic_inguinal_hernia_repair"] and not laterality:
        needs_review.append("Hernia laterality not explicit")

    return {
        "raw_input": raw_input,
        "normalized_input": normalized,
        "procedure": procedure,
        "demographics": demographics,
        "operative_details": operative_details,
        "assumptions": assumptions,
        "confidence": {"procedure": confidence},
        "needs_review": needs_review,
    }
