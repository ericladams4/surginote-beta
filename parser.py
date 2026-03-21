import re

ABBREVIATIONS = {
    "lap chole": "laparoscopic cholecystectomy",
    "robo chole": "robotic cholecystectomy",
    "robotic chole": "robotic cholecystectomy",
    "rob chole": "robotic cholecystectomy",
    "choledocho": "choledocholithiasis",
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
    "n/v/d": "nausea vomiting and diarrhea",
    "sob": "shortness of breath",
    "sbo": "small bowel obstruction",
    "appy": "appendicitis",
    "ccy": "cholecystectomy",
    "ivf": "iv fluids",
    "abx": "antibiotics",
    "ngt": "nasogastric tube",
    "exlap": "exploratory laparotomy",
    "ex lap": "exploratory laparotomy",
    "graham patch": "graham patch repair",
    "mod graham patch": "modified graham patch repair",
    "mod graham": "modified graham patch repair",
    "er": "emergency room",
    "ed": "emergency department",
    "fu": "follow up",
    "f/u": "follow up",
    "nbnb": "non-bloody non-bilious",
    "n/v nbnb": "nausea and vomiting non-bloody non-bilious",
    "pmh": "past medical history",
    "psh": "past surgical history",
    "fh": "family history",
    "sh": "social history",
    "etoh": "alcohol",
    "tob": "tobacco",
    "hx": "history",
}

PROCEDURE_KEYWORDS = {
    "laparoscopic_cholecystectomy": [
        "laparoscopic cholecystectomy",
    ],
    "robotic_cholecystectomy": [
        "robotic cholecystectomy",
        "robotic chole",
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
    "exploratory_laparotomy_with_graham_patch": [
        "exploratory laparotomy",
        "exploratory laparotomy with modified graham patch repair",
        "modified graham patch repair",
        "graham patch repair",
        "perforated gastric ulcer",
    ],
}

DEFAULTS = {}

SYMPTOM_PATTERNS = {
    "abdominal_pain": [
        "abdominal pain",
        "belly pain",
        "right lower quadrant pain",
        "right upper quadrant pain",
        "left lower quadrant pain",
        "left upper quadrant pain",
    ],
    "nausea": ["nausea"],
    "vomiting": ["vomiting", "emesis", "nausea and vomiting"],
    "non_bloody_non_bilious_emesis": [
        "non-bloody non-bilious emesis",
        "non bloody non bilious emesis",
        "non-bloody non-bilious vomiting",
    ],
    "distention": ["distention", "abdominal distention", "bloating"],
    "obstipation": ["obstipation"],
    "constipation": ["constipation"],
    "diarrhea": ["diarrhea"],
    "fever": ["fever", "febrile"],
    "chills": ["chills"],
    "poor_po": ["poor oral intake", "poor po intake", "decreased oral intake"],
    "jaundice": ["jaundice"],
    "anorexia": ["anorexia", "decreased appetite"],
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
        "no acute surgical intervention",
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

PAIN_LOCATIONS = [
    "diffuse",
    "right lower quadrant",
    "left lower quadrant",
    "right upper quadrant",
    "left upper quadrant",
    "epigastric",
    "periumbilical",
    "suprapubic",
    "generalized",
    "lower abdomen",
    "upper abdomen",
    "abdomen",
]

PAIN_INTENSITIES = [
    "mild",
    "moderate",
    "severe",
    "10/10",
    "9/10",
    "8/10",
    "7/10",
    "6/10",
    "5/10",
    "4/10",
    "3/10",
    "2/10",
    "1/10",
]

PAIN_QUALITIES = [
    "sharp",
    "crampy",
    "cramping",
    "burning",
    "stabbing",
    "aching",
    "colicky",
    "pressure",
]

ASSOCIATED_SYMPTOM_MAP = {
    "nausea": "nausea",
    "vomiting": "vomiting",
    "non_bloody_non_bilious_emesis": "non-bloody non-bilious emesis",
    "distention": "abdominal distention",
    "obstipation": "obstipation",
    "constipation": "constipation",
    "diarrhea": "diarrhea",
    "fever": "fever",
    "chills": "chills",
    "poor_po": "decreased oral intake",
    "jaundice": "jaundice",
    "anorexia": "decreased appetite",
}


def normalize_text(text: str) -> str:
    t = text.strip().lower()

    for k in sorted(ABBREVIATIONS.keys(), key=len, reverse=True):
        t = re.sub(rf"\b{re.escape(k)}\b", ABBREVIATIONS[k], t)

    t = re.sub(r"(\d{1,3})\s*yo\s*f\b", r"\1 year old female", t, flags=re.IGNORECASE)
    t = re.sub(r"(\d{1,3})\s*yo\s*m\b", r"\1 year old male", t, flags=re.IGNORECASE)

    t = re.sub(r"[.;,]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def extract_demographics(text: str):
    m = re.search(r"(\d{1,3})\s+year old\s+(female|male)", text)
    if not m:
        return {}
    return {"age": int(m.group(1)), "sex": m.group(2)}


def extract_ports(text: str):
    m = re.search(r"(\d+)\s+ports?\b", text)
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
    patterns = [
        r"surgery consulted for (.+?)(?: with | ct | ultrasound | wbc | lactate | exam | due to |$)",
        r"consulted for (.+?)(?: with | ct | ultrasound | wbc | lactate | exam | due to |$)",
        r"reason for consult (.+?)(?: with | ct | ultrasound | wbc | lactate | exam | due to |$)",
    ]
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            return m.group(1).strip()
    return None


def extract_lab_data(text: str):
    labs = {}

    wbc = re.search(r"wbc\s*(?:of|=)?\s*(\d+(\.\d+)?)", text)
    if wbc:
        labs["wbc"] = wbc.group(1)

    lactate = re.search(r"lactate\s*(?:of|=)?\s*(\d+(\.\d+)?)", text)
    if lactate:
        labs["lactate"] = lactate.group(1)

    hgb = re.search(r"hgb\s*(?:of|=)?\s*(\d+(\.\d+)?)", text)
    if hgb:
        labs["hgb"] = hgb.group(1)

    bili = re.search(r"(?:bilirubin|bili)\s*(?:of|=)?\s*(\d+(\.\d+)?)", text)
    if bili:
        labs["bilirubin"] = bili.group(1)

    alk_phos = re.search(r"(?:alk phos|alkaline phosphatase)\s*(?:of|=)?\s*(\d+(\.\d+)?)", text)
    if alk_phos:
        labs["alk_phos"] = alk_phos.group(1)

    ast = re.search(r"\bast\b\s*(?:of|=)?\s*(\d+(\.\d+)?)", text)
    if ast:
        labs["ast"] = ast.group(1)

    alt = re.search(r"\balt\b\s*(?:of|=)?\s*(\d+(\.\d+)?)", text)
    if alt:
        labs["alt"] = alt.group(1)

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
        ("rebound", "rebound"),
        ("guarding", "guarding"),
        ("distended", "distended"),
        ("soft", "soft"),
        ("non_toxic", "non toxic"),
    ]

    for key, phrase in patterns:
        if phrase in text:
            findings.append(key)

    return findings


def extract_pmh(text: str):
    explicit = re.search(
        r"(?:\bpast medical history\b|\bpmh\b)\s*(?:is|:)?\s*(.+?)(?:(?:\bpast surgical history\b|\bpsh\b|\bfamily history\b|\bfh\b|\bsocial history\b|\bsh\b|\breview of systems\b|\bros\b|\bobjective\b|\bassessment\b|\bplan\b)|$)",
        text
    )
    if explicit:
        return explicit.group(1).strip()

    pmh_terms = [
        "diabetes", "hypertension", "hyperlipidemia", "coronary artery disease",
        "cad", "atrial fibrillation", "afib", "copd", "asthma", "gerd",
        "cirrhosis", "ckd", "chronic kidney disease", "heart failure",
        "congestive heart failure", "cancer", "malignancy", "obesity",
        "diverticulitis", "gallstones", "cholelithiasis", "appendicitis",
        "small bowel obstruction", "crohn", "ulcerative colitis",
        "primary biliary cholangitis", "pbc", "pancreatitis", "choledocholithiasis",
    ]
    found = [term for term in pmh_terms if term in text]
    return ", ".join(sorted(set(found))) if found else None


def extract_psh(text: str):
    explicit = re.search(
        r"(?:\bpast surgical history\b|\bpsh\b)\s*(?:is|:)?\s*(.+?)(?:(?:\bfamily history\b|\bfh\b|\bsocial history\b|\bsh\b|\breview of systems\b|\bros\b|\bobjective\b|\bassessment\b|\bplan\b)|$)",
        text
    )
    if explicit:
        return explicit.group(1).strip()

    psh_patterns = [
        "status post open colectomy",
        "status post colectomy",
        "status post appendectomy",
        "status post cholecystectomy",
        "status post ercp",
        "prior open colectomy",
        "prior laparotomy",
        "prior abdominal surgery",
        "prior appendectomy",
        "prior cholecystectomy",
        "prior hernia repair",
        "ercp",
    ]
    found = [p for p in psh_patterns if p in text]
    return ", ".join(sorted(set(found))) if found else None


def extract_family_history(text: str):
    explicit = re.search(
        r"(?:\bfamily history\b|\bfh\b)\s*(?:is|:)?\s*(.+?)(?:(?:\bsocial history\b|\bsh\b|\breview of systems\b|\bros\b|\bobjective\b|\bassessment\b|\bplan\b)|$)",
        text
    )
    if explicit:
        value = explicit.group(1).strip()
        if value:
            return value

    if "family history non contributory" in text or "family history non-contributory" in text:
        return "Non-contributory."

    return None


def extract_social_history(text: str):
    explicit = re.search(
        r"(?:\bsocial history\b|\bsh\b)\s*(?:is|:)?\s*(.+?)(?:(?:\breview of systems\b|\bros\b|\bobjective\b|\bassessment\b|\bplan\b)|$)",
        text
    )
    if explicit:
        value = explicit.group(1).strip()
        if value:
            return value

    pieces = []

    if "denies alcohol" in text or "no alcohol" in text:
        pieces.append("Denies alcohol use")
    elif "alcohol use" in text:
        pieces.append("Alcohol use")

    if "denies tobacco" in text or "no tobacco" in text or "non smoker" in text or "nonsmoker" in text:
        pieces.append("Denies tobacco use")
    elif "tobacco use" in text or "smoker" in text:
        pieces.append("Tobacco use")

    if "denies drug use" in text or "no drug use" in text:
        pieces.append("Denies drug use")
    elif "drug use" in text or "illicit drug use" in text:
        pieces.append("Drug use")

    if pieces:
        return ", ".join(pieces) + "."

    return None


def extract_pain_characteristics(text: str, symptoms):
    pain = {}

    if "pain" not in text and "abdominal pain" not in text:
        return pain

    for location in PAIN_LOCATIONS:
        if location in text:
            pain["location"] = location
            break

    for intensity in PAIN_INTENSITIES:
        if intensity in text:
            pain["intensity"] = intensity
            break

    for quality in PAIN_QUALITIES:
        if quality in text:
            pain["quality"] = quality
            break

    duration_patterns = [
        r"(\d+\s*hours?\s*ago)",
        r"(\d+\s*days?\s*ago)",
        r"(\d+\s*weeks?\s*ago)",
        r"for\s+(\d+\s*hours?)",
        r"for\s+(\d+\s*days?)",
        r"for\s+(\d+\s*weeks?)",
        r"x\s*(\d+\s*hours?)",
        r"x\s*(\d+\s*days?)",
        r"x\s*(\d+\s*weeks?)",
        r"beginning\s+(\d+\s*hours?\s*ago)",
        r"starting\s+(\d+\s*hours?\s*ago)",
    ]
    for pattern in duration_patterns:
        m = re.search(pattern, text)
        if m:
            pain["duration"] = m.group(1).strip()
            break

    ex_patterns = [
        r"(worse with [a-z\s]+)",
        r"(better with [a-z\s]+)",
        r"(improved with [a-z\s]+)",
        r"(relieved by [a-z\s]+)",
        r"(aggravated by [a-z\s]+)",
        r"(exacerbated by [a-z\s]+)",
    ]
    ex_factors = []
    for pattern in ex_patterns:
        matches = re.findall(pattern, text)
        ex_factors.extend(matches)
    if ex_factors:
        pain["modifying_factors"] = "; ".join(sorted(set(ex_factors)))
    else:
        pain["modifying_factors"] = "no specific exacerbating or alleviating factors"

    assoc = []
    for key in symptoms:
        if key in ASSOCIATED_SYMPTOM_MAP:
            assoc.append(ASSOCIATED_SYMPTOM_MAP[key])
    if assoc:
        pain["associated_symptoms"] = sorted(set(assoc))

    return pain


def extract_ros(text, symptoms):
    ros = {
        "constitutional": "Negative except as noted in HPI.",
        "cardiovascular": "Negative.",
        "respiratory": "Negative.",
        "genitourinary": "Negative.",
        "neurologic": "Negative.",
    }

    gi_parts = []
    if "abdominal_pain" in symptoms:
        gi_parts.append("abdominal pain")
    if "nausea" in symptoms:
        gi_parts.append("nausea")
    if "vomiting" in symptoms:
        gi_parts.append("vomiting")
    if "non_bloody_non_bilious_emesis" in symptoms:
        gi_parts.append("non-bloody non-bilious emesis")
    if "distention" in symptoms:
        gi_parts.append("abdominal distention")
    if "obstipation" in symptoms:
        gi_parts.append("obstipation")
    if "constipation" in symptoms:
        gi_parts.append("constipation")
    if "diarrhea" in symptoms:
        gi_parts.append("diarrhea")
    if "poor_po" in symptoms:
        gi_parts.append("decreased oral intake")
    if "jaundice" in symptoms:
        gi_parts.append("jaundice")

    if gi_parts:
        ros["gastrointestinal"] = "Positive for " + ", ".join(sorted(set(gi_parts))) + "."
    else:
        ros["gastrointestinal"] = "Negative."

    if "fever" in symptoms or "chills" in symptoms:
        const_parts = []
        if "fever" in symptoms:
            const_parts.append("fever")
        if "chills" in symptoms:
            const_parts.append("chills")
        ros["constitutional"] = "Positive for " + ", ".join(const_parts) + "."

    return ros


def build_hpi_symptom_summary(pain_characteristics):
    if not pain_characteristics:
        return None

    parts = []

    location = pain_characteristics.get("location")
    intensity = pain_characteristics.get("intensity")
    quality = pain_characteristics.get("quality")

    descriptor_bits = [bit for bit in [location, intensity, quality] if bit]
    if descriptor_bits:
        parts.append(" ".join(descriptor_bits) + " pain")

    duration = pain_characteristics.get("duration")
    if duration:
        parts.append(f"starting {duration}")

    assoc = pain_characteristics.get("associated_symptoms") or []
    if assoc:
        parts.append("associated with " + ", ".join(assoc))

    modifying = pain_characteristics.get("modifying_factors")
    if modifying:
        parts.append(modifying)

    return ", ".join(parts) if parts else None


def extract_hospital_course(text: str):
    course = {}

    if "admitted to medicine" in text:
        course["admission_service"] = "admitted to medicine"
    elif "admitted to surgery" in text:
        course["admission_service"] = "admitted to surgery"
    elif "admitted" in text:
        course["admission_service"] = "admitted"
    elif "emergency department" in text:
        course["admission_service"] = "seen in the emergency department"

    if "hospitalized" in text:
        course["hospitalized"] = True

    if "recent ercp" in text or "status post ercp" in text or "ercp" in text:
        course["recent_procedure"] = "recent ERCP"

    if "post ercp pancreatitis" in text or "post-ercp pancreatitis" in text:
        course["complication"] = "prior post-ERCP pancreatitis"

    return course


def extract_formal_exam_defaults(text: str, exam_findings):
    exam = {
        "gen": "No acute distress, comfortable",
        "heent": "Normocephalic, atraumatic",
        "pulmonary": "Normal work of breathing",
        "cardiovascular": "Warm and well perfused",
        "abdomen": "Soft, non-tender, non-distended, no guarding, no hernias or masses appreciated",
    }

    if "appendicitis" in text:
        exam["abdomen"] = "Soft, focal right lower quadrant tenderness to palpation"
    elif "cholecystitis" in text:
        exam["abdomen"] = "Soft, focal right upper quadrant tenderness to palpation"

    if "distended" in exam_findings:
        exam["abdomen"] = "Soft, mildly distended"
    if "tenderness" in exam_findings:
        exam["abdomen"] = "Soft, tender to palpation"
    if "mild_tenderness" in exam_findings:
        exam["abdomen"] = "Soft, mildly tender to palpation"
    if "diffuse_tenderness" in exam_findings:
        exam["abdomen"] = "Soft, mildly diffusely tender to palpation"
    if "focal_tenderness" in exam_findings and "right lower quadrant" in text:
        exam["abdomen"] = "Soft, focal right lower quadrant tenderness to palpation"
    elif "focal_tenderness" in exam_findings:
        exam["abdomen"] = "Soft, focal tenderness to palpation"

    if "guarding" in exam_findings:
        exam["abdomen"] = exam["abdomen"].rstrip(".") + ", with guarding"
    if "rebound" in exam_findings:
        exam["abdomen"] = exam["abdomen"].rstrip(".") + ", with rebound tenderness"
    if "no_peritonitis" in exam_findings and "peritonitis" not in exam["abdomen"]:
        exam["abdomen"] = exam["abdomen"].rstrip(".") + ", no peritonitis"

    return exam


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
    pmh = extract_pmh(normalized)
    psh = extract_psh(normalized)
    family_history = extract_family_history(normalized)
    social_history = extract_social_history(normalized)
    pain_characteristics = extract_pain_characteristics(normalized, symptoms)
    ros = extract_ros(normalized, symptoms)
    hpi_symptom_summary = build_hpi_symptom_summary(pain_characteristics)
    hospital_course = extract_hospital_course(normalized)
    formal_exam = extract_formal_exam_defaults(normalized, exam_findings)

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
    if pmh:
        clinical_context["past_medical_history"] = pmh
    if psh:
        clinical_context["past_surgical_history"] = psh
    if family_history:
        clinical_context["family_history"] = family_history
    if social_history:
        clinical_context["social_history"] = social_history
    if pain_characteristics:
        clinical_context["pain_characteristics"] = pain_characteristics
    if hpi_symptom_summary:
        clinical_context["hpi_symptom_summary"] = hpi_symptom_summary
    if ros:
        clinical_context["review_of_systems"] = ros
    if hospital_course:
        clinical_context["hospital_course"] = hospital_course
    if formal_exam:
        clinical_context["formal_exam"] = formal_exam

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

    if note_context == "consult_note" and not family_history:
        assumptions["family_history_default"] = "Non-contributory."

    if note_context == "consult_note" and not social_history:
        assumptions["social_history_default"] = "Non-contributory."

    if note_context == "consult_note" and not pain_characteristics.get("modifying_factors"):
        assumptions["modifying_factors_default"] = "no specific exacerbating or alleviating factors"

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
