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
- clear procedural narrative
- include procedure performed, findings, technique, specimen, estimated blood loss, drains, and complications if supported
- structure like a real operative report
- avoid clinic- or consult-style assessment/plan sections unless clearly relevant
""",
    "clinic_note": """
Generate a polished clinic note appropriate for a general surgeon.

Priorities:
- outpatient tone
- concise but useful documentation
- focus on evaluation, interval history, symptoms, decision-making, and treatment planning
- avoid unnecessary narrative or repetition
- do not force operative sections unless clearly relevant

Preferred style:
- sound like a real general surgery office note
- if this appears to be a preoperative visit, emphasize surgical problem, workup, impression, and next-step planning
- if this appears to be a postoperative clinic visit, emphasize recovery course, symptoms, pathology/imaging discussion, and follow-up
- assessment should synthesize rather than simply repeat the history
- plan should be practical and succinct
""",
    "consult_note": """
Generate a concise surgical consult note appropriate for an inpatient or ED consultation.

Priorities:
- brief, clinically useful, attending-style documentation
- emphasize the reason for consultation, the key clinical facts, the surgical impression, and actionable recommendations
- avoid filler, repetition, and textbook explanations
- total length should generally remain short unless the source material truly requires more detail

Formatting requirements:
- use the section header exactly as: Assessment and Plan:
- within Assessment and Plan, first write a short assessment paragraph
- then leave one blank line
- then write the plan as bullet points
- never number the assessment
- never number the plan

Consult style rules:
- HPI should usually be brief (1–3 short sentences)
- only include exam, labs, or imaging sections if supported and useful
- do not force sections that are not supported by the source material
- keep the note focused on surgical reasoning and recommendations
""",
}

GLOBAL_RULES = """
Global rules:
- Use only facts supported by the source material and structured case facts.
- Do not invent medications, vital signs, exam findings, imaging results, lab values, PMH, PSH, allergies, or operative details unless reasonably supported by the source material.
- If specific details are missing, omit them or use neutral phrasing rather than fabricate.
- Resolve shorthand into polished professional language.
- Preserve medical accuracy and a surgeon's voice.
- Output only the final note.
- Do not include commentary, bullet explanations, or meta-text outside the note itself.
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

DYNAMIC_FORMATTER_GUIDANCE = """
Dynamic formatting rules:
- Only include sections that are actually supported by the case facts and useful for the note type.
- Do not force rigid templates when the available source material is sparse.
- If data are limited, write a shorter note with fewer sections.
- If the case supports more detail, expand naturally while staying concise.
- Prefer realistic clinical formatting over completeness for its own sake.
- The note should feel like something a practicing surgeon would actually write in workflow.
"""


def _build_note_specific_guidance(note_type: str) -> str:
    if note_type == "op_note":
        return """
Additional operative note guidance:
- Make the Description of Procedure the strongest section.
- Ensure the procedural sequence is coherent and technically believable based on the supplied facts.
- If assumptions are present in the case facts, incorporate them only when they are standard, low-risk defaults and not contradicted by the source material.
- If procedure identity is uncertain, keep the wording conservative.
- If the example note uses a surgeon-specific operative structure, mirror that structure when appropriate.
- Preferred op note sections may include:
  - Preoperative Diagnosis
  - Postoperative Diagnosis
  - Procedure
  - Indication
  - Findings
  - Description of Procedure
  - Specimen
  - Estimated Blood Loss
  - Drains
  - Complications
  - Disposition
- Omit unsupported sections rather than fabricate them.
"""
    if note_type == "clinic_note":
        return """
Additional clinic note guidance:
- Write like a real general surgery office note.
- Use dynamic formatting based on the visit type and available facts.
- If the source suggests preoperative evaluation, emphasize the problem, supporting workup, assessment, and next steps.
- If the source suggests postoperative follow-up, emphasize interval recovery, symptoms, pathology or imaging review, wound status if supported, and follow-up plan.
- Assessment should be concise and synthetic rather than repetitive.
- Plan can be brief and practical.
- Common useful clinic sections may include:
  - Chief Complaint or Reason for Visit
  - HPI
  - Relevant Workup
  - Assessment
  - Plan
- Do not force physical exam or review of systems unless supported and useful.
- If the example note has a distinctive clinic flow or plan style, try to match it when appropriate.
"""
    if note_type == "consult_note":
        return """
Additional consult note guidance:
- Write like a real inpatient or emergency general surgery consult.
- Make it clear what question surgery is being asked to address.
- Use dynamic formatting: include only sections supported by the case and useful for the consult.
- If supported, useful consult sections may include:
  - Reason for Consult
  - HPI
  - Pertinent Findings
  - Assessment and Plan
- The Assessment and Plan section is the most important part of the note.

Assessment and Plan expectations:
- Start with a short assessment paragraph, not bullets and not numbering.
- The assessment paragraph should include:
  - a brief opening statement summarizing the patient and surgical issue
  - the most likely diagnosis or leading differential if not yet definitive
  - concise clinical reasoning linking the diagnosis to symptoms, exam, labs, and/or imaging
  - the rationale for operative versus nonoperative management
- After the assessment paragraph, leave one blank line.
- Then provide the plan as bullet points only.
- Each bullet should contain one actionable recommendation.
- Never number the plan.

- If the consult is sparse, keep the entire note very short.
- If the consult is for a condition not clearly requiring surgery, recommendations should still sound useful, grounded, and surgeon-like.
- If the example note has a distinctive consult structure or recommendation style, try to match it when appropriate.
"""
    return ""


def _build_reasoning_layer(note_type: str) -> str:
    if note_type == "consult_note":
        return """
Before writing the note, internally reason through the following:
1. What is the surgical question or reason for consult?
2. What is the most likely diagnosis or primary surgical issue?
3. What supporting facts matter most (symptoms, exam, imaging, labs)?
4. Does the patient appear to need operative intervention, further workup, or conservative management?
5. What is the shortest, clearest way to communicate the assessment and recommendations?

Do not output these reasoning steps.
Only output the final note.
"""
    if note_type == "clinic_note":
        return """
Before writing the note, internally reason through the following:
1. What type of visit is this (new evaluation, preoperative discussion, postoperative follow-up, other)?
2. What is the main surgical problem or reason for visit?
3. What facts most strongly influence decision-making?
4. What is the clearest and most concise assessment?
5. What plan would a surgeon actually document in clinic?

Do not output these reasoning steps.
Only output the final note.
"""
    return """
Before writing the note, internally reason through the following:
1. What is the key procedural or surgical issue?
2. What are the most important facts to communicate?
3. What sections are actually supported by the case?
4. What is the clearest and most concise way to document the case?

Do not output these reasoning steps.
Only output the final note.
"""


def build_prompt(case_facts, note_type="op_note", template_content=None):
    note_type = note_type if note_type in NOTE_TYPE_LABELS else "op_note"
    note_label = NOTE_TYPE_LABELS[note_type]
    note_instructions = NOTE_TYPE_INSTRUCTIONS[note_type]
    note_specific_guidance = _build_note_specific_guidance(note_type)
    reasoning_layer = _build_reasoning_layer(note_type)

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

{DYNAMIC_FORMATTER_GUIDANCE}

{GLOBAL_RULES}

{reasoning_layer}

Structured case facts and source material:
{case_json}

{template_section}

Final output requirements:
- Produce a complete final {note_label}
- Use polished medical prose and realistic section headings
- Make the note ready for physician review and editing
- Use only the sections supported by the case and useful for the note type
"""