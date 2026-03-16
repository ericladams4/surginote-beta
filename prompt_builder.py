import json

NOTE_TYPE_LABELS = {
    "op_note": "operative note",
    "clinic_note": "clinic note",
    "consult_note": "consult note",
}

NOTE_TYPE_INSTRUCTIONS = {
    "op_note": """
Generate a polished operative note appropriate for a general surgeon.

Priorities:
- concise but complete operative documentation
- include the core procedural story in a natural operative-note format
- include procedure performed, indication, key findings, operative technique, specimen, estimated blood loss, drains, and complications if supported
- maintain a professional operative tone
- do not include clinic-style assessment/plan formatting unless clearly appropriate

Preferred structure when supported:
- Preoperative Diagnosis
- Postoperative Diagnosis
- Procedure
- Surgeon / Assistants if supported
- Anesthesia if supported
- Indication
- Findings
- Description of Procedure
- Specimen
- Estimated Blood Loss
- Drains
- Complications
- Disposition
""",
    "clinic_note": """
Generate a polished clinic note appropriate for a general surgeon.

Priorities:
- outpatient clinical tone
- emphasize evaluation, interval history, symptoms, decision-making, and treatment planning
- organize clearly and read like a real follow-up or new-patient surgical clinic note
- do not force operative sections unless clearly relevant
- if the patient is being evaluated for surgery, clearly present the problem, relevant workup, impression, and plan
- if this appears to be a postoperative clinic visit, reflect that naturally

Preferred structure when supported:
- Chief Complaint or Reason for Visit
- History of Present Illness
- Relevant Past Surgical / Medical History if supported
- Imaging / Labs / Prior Workup if supported
- Physical Exam if supported
- Assessment
- Plan

Writing guidance:
- make the Assessment and Plan clinically useful and surgeon-like
- if details are limited, keep the note concise rather than padded
- if surgical options, risks, follow-up, diet, wound care, or return precautions are supported, integrate them naturally
""",
   "consult_note": """
Generate a concise surgical consult note appropriate for a busy general surgeon.

Priorities:
- concise documentation appropriate for inpatient or ED consults
- avoid unnecessary narrative or repetition
- short HPI (1–3 sentences maximum)
- focused exam only if relevant
- assessment in bullet form
- plan in clear bullet points
- total length should generally be under ~150 words unless clinically necessary

Suggested structure:

Reason for consult:
One short sentence.

HPI:
Brief summary of key clinical facts only.

Pertinent findings:
Relevant labs, imaging, or exam findings if available.

Assessment:
Write a focused surgical assessment that reflects clinical reasoning. The assessment should include:

1. Opening statement
A one-sentence summary identifying the patient, key clinical context, and the primary surgical issue.

Example format:
"[Age]-year-old [sex] with [relevant background] presenting with [primary surgical problem]."

2. Impression / Diagnosis
Clearly state the most likely diagnosis and suspected etiology.
If the diagnosis is not definitive, briefly list the leading differential diagnoses.

3. Clinical reasoning
Briefly connect the available clinical information to the diagnosis.
Reference relevant symptoms, exam findings, laboratory results, or imaging that support the impression.

4. Surgical decision-making
Explain the rationale for operative versus non-operative management.
Document why surgical intervention is appropriate, or why conservative management is recommended.

Style guidance:
- Keep the assessment concise (typically 3–5 sentences).
- Avoid repeating the entire history.
- Focus on synthesis and decision-making rather than description.
- Write in the tone of a real surgical consult note.

Plan:
• imaging  
• operative vs nonoperative management  
• consult recommendations  
• follow-up

Avoid:
- long narrative paragraphs
- repeating the same information in multiple sections
- textbook explanations
"""

GLOBAL_RULES = """
Global rules:
- Use only facts supported by the source material and structured case facts.
- Do not invent medications, vital signs, exam findings, imaging results, lab values, PMH, PSH, allergies, or operative details unless they are reasonably implied by the provided source material.
- If specific details are missing, omit them or use neutral phrasing rather than fabricate.
- Resolve shorthand into polished professional language.
- Preserve medical accuracy and a surgeon's voice.
- Output only the final note.
- Do not include commentary, bullet explanations, or meta-text.
"""

TEMPLATE_GUIDANCE = """
The user has provided a preferred template or example note.

Use it as guidance for:
- structure
- section headings
- formatting
- writing style
- degree of detail

Aim to make the output resemble the template when appropriate for the current case.

Do not copy irrelevant, stale, or patient-specific content from the template.
Do not carry forward details that are not supported by the current source material.
If the current case does not fit a section from the template, omit or adapt that section naturally.
"""

def _build_note_specific_guidance(note_type: str) -> str:
    if note_type == "op_note":
        return """
Additional operative note guidance:
- Make the Description of Procedure the strongest section.
- Ensure the procedural sequence is coherent and technically believable based on the supplied facts.
- If assumptions are present in the case facts, you may incorporate them carefully only when they are standard, low-risk defaults and not contradicted by the source material.
- If procedure identity is uncertain, keep the wording conservative.
- If the example note uses a surgeon-specific operative structure, mirror that structure when appropriate to the current case.
"""
    if note_type == "clinic_note":
        return """
Additional clinic note guidance:
- Write like a real general surgery office note.
- If the source suggests preoperative evaluation, explain the surgical problem, relevant workup, and next-step planning.
- If the source suggests postoperative follow-up, focus on recovery course, symptoms, wound issues, diet, bowel function, pathology or imaging discussion, and follow-up plan if supported.
- The Assessment should synthesize the clinical situation, not merely restate the history.
- The Plan should sound practical and specific, but only include items supported by the source material.
- If the example note has a distinctive clinic flow or plan style, try to match it when appropriate.
"""
    if note_type == "consult_note":
        return """
Additional consult note guidance:
- Write like a real inpatient or emergency general surgery consult.
- Make it clear what question the primary team or ED is asking surgery to answer.
- The Assessment should state the likely surgical problem or differential when supported.
- The Plan should clearly communicate recommendation(s): operative vs nonoperative management, further workup, monitoring, antibiotics, diet status, admission/disposition, follow-up, or reassessment as appropriate.
- If the consult is for a condition not clearly requiring surgery, the recommendations should still sound useful and authoritative.
- If the example note has a distinctive consult structure or recommendation style, try to match it when appropriate.
"""
    return ""


def build_prompt(case_facts, note_type="op_note", template_content=None):
    note_type = note_type if note_type in NOTE_TYPE_LABELS else "op_note"
    note_label = NOTE_TYPE_LABELS[note_type]
    note_instructions = NOTE_TYPE_INSTRUCTIONS[note_type]
    note_specific_guidance = _build_note_specific_guidance(note_type)

    case_json = json.dumps(case_facts, indent=2)

    template_section = ""
    if template_content:
        template_section = f"""
{TEMPLATE_GUIDANCE}

USER TEMPLATE / EXAMPLE NOTE:
{template_content}
"""

    return f"""
You are an expert surgical documentation assistant helping draft high-quality notes for a general surgeon.

Your task is to generate a polished {note_label}.

{note_instructions}

{note_specific_guidance}

{GLOBAL_RULES}

Structured case facts and source material:
{case_json}

{template_section}

Final output requirements:
- Produce a complete final {note_label}
- Use polished medical prose and realistic section headings
- Make the note ready for physician review and editing
"""