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
    "rlq": "right lower quadrant",
    "ruq": "right upper quadrant",
    "llq": "left lower quadrant",
    "luq": "left upper quadrant",
    "n/v": "nausea and vomiting",
    "sob": "small bowel obstruction",
    "sbo": "small bowel obstruction",
    "appy": "appendicitis",
    "ccy": "cholecystectomy",
    "ivf": "iv fluids",
    "abx": "antibiotics",
    "ngt": "nasogastric tube",
    "er": "emergency room",
    "ed": "emergency department",
    "fu": "follow up",
    "f/u": "follow up",
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
    "laparoscopic_appendectomy": [
        "laparoscopic appendectomy",
        "appendectomy",
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
    "laparoscopic_appendectomy": {
        "ebl": "minimal",
        "drain": "none",
        "specimen": "appendix",
        "complications": "none",
    },
}

SYMPTOM_PATTERNS = {
    "abdominal_pain": [
        "abdominal pain",
        "belly pain",
        "right lower quadrant pain",
        "right upper quadrant pain",
        "left lower quadrant pain",
        "left upper quadrant pain",
        "pain",
    ],
    "nausea": ["nausea"],
    "vomiting": ["vomiting", "emesis", "nausea and vomiting"],
    "distention": ["distention", "abdominal distention", "bloating"],
    "obstipation": ["obstipation"],
    "constipation": ["constipation"],
    "diarrhea": ["diarrhea"],
    "fever": ["fever", "febrile"],
    "chills": ["chills"],
    "poor_po": ["poor oral intake", "poor po intake", "decreased oral intake"],
    "jaundice": ["jaundice"],
}

IMAGING_PATTERNS = {
    "ct_appendicitis": [
        "ct with appendicitis",
        "ct shows appendicitis",
        "ct concerning for appendicitis",
        "imaging consistent with appendicitis",
    ],
    "ct_sbo": [
        "ct with small bowel obstruction",
        "ct shows small bowel obstruction",
        "ct with transition point",
        "transition point",
    ],
    "ultrasound_gallstones": [
        "ultrasound with gallstones",
        "gallstones on ultrasound",
        "right upper quadrant ultrasound with gallstones",
    ],
    "ct_cholecystitis": [
        "ct with cholecystitis",
        "ct shows cholecystitis",
    ],
}

PLAN_PATTERNS = {
    "operative_management": [
        "recommend surgery",
        "proceed to operating room",
        "proceed with surgery",
        "laparoscopic appendectomy",
        "laparoscopic cholecystectomy",
        "operative management",
        "or today",
    ],
    "nonoperative_management": [
        "nonoperative management",
        "conservative management",
        "observation",
    ],
    "npo": ["npo", "nothing by mouth"],
    "iv_fluids": ["iv fluids"],
    "antibiotics": ["antibiotics", "iv antibiotics", "abx"],
    "serial_exams": ["serial abdominal exams", "serial exams"],
    "bowel_rest": ["bowel rest"],
    "ngt": ["nasogastric tube", "ngt"],
    "follow_up": ["follow up", "outpatient follow up", "return to clinic"],
    "admit": ["admit", "admission"],
    "discharge": ["discharge", "ok for discharge"],
}

CONSULT_PATTERNS = [
    "surgery consulted",
    "consulted for",
    "general surgery consulted",
    "surgical consult",
    "reason for consult",
    "ed consult",
    "emergency department consult",
    "inpatient consult",
]

CLINIC_PATTERNS = [
    "seen in clinic",
    "clinic visit",
    "follow up visit",
    "post op visit",
    "postoperative visit",
    "new patient visit",
    "office visit",
]

POSTOP_PATTERNS = [
    "post op",
    "postoperative",
    "status post",
    "follow up after",
]

PREOP_PATTERNS = [
    "discussed surgery",
    "wishes to proceed",
    "consented for surgery",
    "preoperative evaluation",
    "evaluate for surgery",
]

NONOPERATIVE_PATTERNS = [
    "nonoperative management",
    "conservative management",
    "observation",
    "no acute surgical intervention",
]

OPERATIVE_PATTERNS = [
    "procedure",
    "port",
    "estimated blood loss",
    "critical view",
    "gallbladder removed",
    "specimen",
    "drain",
    "operative",
]


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
    if "right lower quadrant" in text:
        return "right lower quadrant"
    if "right upper quadrant" in text:
        return "right upper quadrant"
    if "left lower quadrant" in text:
        return "left lower quadrant"
    if "left upper quadrant" in text:
        return "left upper quadrant"
    return None


def extract_defect_type(text: str):
    if "direct defect" in text:
        return "direct"
    if "indirect defect" in text:
        return "indirect"
    return None


def extract_consult_context(text: str):
    if any(p in text for p in CONSULT_PATTERNS):
        return "consult"
    if any(p in text for p in CLINIC_PATTERNS):
        return "clinic"
    if any(p in text for p in OPERATIVE_PATTERNS):
        return "operative"
    return None


def extract_visit_context(text: str):
    if any(p in text for p in POSTOP_PATTERNS):
        return "postoperative_follow_up"
    if any(p in text for p in PREOP_PATTERNS):
        return "preoperative_evaluation"
    if any(p in text for p in CLINIC_PATTERNS):
        return "clinic_visit"
    if any(p in text for p in CONSULT_PATTERNS):
        return "surgical_consult"
    return None


def extract_symptoms(text: str):
    found = []
    for symptom, patterns in SYMPTOM_PATTERNS.items():
        if any(p in text for p in patterns):
            found.append(symptom)
    return found


def extract_imaging(text: str):
    found = []
    for study, patterns in IMAGING_PATTERNS.items():
        if any(p in text for p in patterns):
            found.append(study)
    return found


def extract_plans(text: str):
    found = []
    for item, patterns in PLAN_PATTERNS.items():
        if any(p in text for p in patterns):
            found.append(item)
    return found


def extract_consult_question(text: str):
    if "consulted for" in text:
        m = re.search(r'consulted for (.+?)(?: with | ct | wbc | surgery |$)', text)
        if m:
            return m.group(1).strip()
    if "reason for consult" in text:
        m = re.search(r'reason for consult (.+?)(?: with | ct | wbc | surgery |$)', text)
        if m:
            return m.group(1).strip()
    if "surgery consulted for" in text:
        m = re.search(r'surgery consulted for (.+?)(?: with | ct | wbc | surgery |$)', text)
        if m:
            return m.group(1).strip()
    return None


def extract_lab_data(text: str):
    labs = {}

    wbc = re.search(r'wbc\s*(?:of|=)?\s*(\d+(\.\d+)?)', text)
    if wbc:
        labs["wbc"] = wbc.group(1)

    lactate = re.search(r'lactate\s*(?:of|=)?\s*(\d+(\.\d+)?)', text)
    if lactate:
        labs["lactate"] = lactate.group(1)

    if "labs within normal limits" in text or "labs wnl" in text or "within normal limits" in text:
        labs["labs_summary"] = "within normal limits"

    return labs


def extract_exam_findings(text: str):
    findings = []

    patterns = [
        ("peritonitis", "peritonitis"),
        ("no_peritonitis", "no peritonitis"),
        ("tenderness", "tenderness"),
        ("mild_tenderness", "mild tenderness"),
        ("diffuse_tenderness", "diffuse tenderness"),
        ("focal_tenderness", "focal tenderness"),
        ("distended", "distended"),
        ("soft", "soft"),
    ]

    for key, phrase in patterns:
        if phrase in text:
            findings.append(key)

    return findings


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


def infer_note_context(text: str):
    consult_score = sum(1 for p in CONSULT_PATTERNS if p in text)
    clinic_score = sum(1 for p in CLINIC_PATTERNS + POSTOP_PATTERNS + PREOP_PATTERNS if p in text)
    operative_score = sum(1 for p in OPERATIVE_PATTERNS if p in text)

    scores = {
        "consult_note": consult_score,
        "clinic_note": clinic_score,
        "op_note": operative_score,
    }

    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return None, 0.0

    total = sum(scores.values()) or 1
    return best, round(scores[best] / total, 2)


def build_case_facts(raw_input: str):
    normalized = normalize_text(raw_input)
    demographics = extract_demographics(normalized)
    procedure, procedure_confidence = classify_procedure(normalized)
    note_context, note_context_confidence = infer_note_context(normalized)
    ports = extract_ports(normalized)
    laterality = extract_laterality(normalized)
    defect_type = extract_defect_type(normalized)
    consult_context = extract_consult_context(normalized)
    visit_context = extract_visit_context(normalized)
    symptoms = extract_symptoms(normalized)
    imaging = extract_imaging(normalized)
    plans = extract_plans(normalized)
    consult_question = extract_consult_question(normalized)
    labs = extract_lab_data(normalized)
    exam_findings = extract_exam_findings(normalized)

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

    clinical_context = {}
    if consult_context:
        clinical_context["context"] = consult_context
    if visit_context:
        clinical_context["visit_type"] = visit_context
    if consult_question:
        clinical_context["consult_question"] = consult_question
    if symptoms:
        clinical_context["symptoms"] = symptoms
    if imaging:
        clinical_context["imaging"] = imaging
    if plans:
        clinical_context["plan_signals"] = plans
    if labs:
        clinical_context["labs"] = labs
    if exam_findings:
        clinical_context["exam_findings"] = exam_findings

    assumptions = DEFAULTS.get(procedure, {}).copy()
    needs_review = []

    if procedure is None and note_context == "op_note":
        needs_review.append("Procedure unclear")

    if procedure in ["open_inguinal_hernia_repair", "robotic_inguinal_hernia_repair"] and not laterality:
        needs_review.append("Hernia laterality not explicit")

    if note_context == "consult_note" and not consult_question:
        needs_review.append("Reason for consult not explicit")

    if note_context == "clinic_note" and not visit_context:
        needs_review.append("Clinic visit type not explicit")

    if note_context == "consult_note" and not plans:
        needs_review.append("Plan/recommendation not explicit")

    if any(p in normalized for p in NONOPERATIVE_PATTERNS):
        assumptions["management_direction"] = "nonoperative"
    elif any(p in normalized for p in PLAN_PATTERNS["operative_management"]):
        assumptions["management_direction"] = "operative"

    return {
        "raw_input": raw_input,
        "normalized_input": normalized,
        "procedure": procedure,
        "note_context": note_context,
        "demographics": demographics,
        "operative_details": operative_details,
        "clinical_context": clinical_context,
        "assumptions": assumptions,
        "confidence": {
            "procedure": procedure_confidence,
            "note_context": note_context_confidence,
        },
        "needs_review": needs_review,
    }