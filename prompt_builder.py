import json
import re

NOTE_TYPE_LABELS = {
    "op_note": "operative note",
    "clinic_note": "clinic note",
    "consult_note": "consult note",
}

SUPPORTED_TEMPLATE_PLACEHOLDERS = {
    "reason_for_consult",
    "hpi",
    "pmh",
    "psh",
    "fh",
    "sh",
    "ros",
    "objective",
    "assessment",
    "plan",
    "procedure",
    "findings",
    "description_of_procedure",
    "specimen",
    "estimated_blood_loss",
    "drains",
    "complications",
    "disposition",
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
- if this appears to be a preoperative visit, emphasize surgical problem, supporting workup, impression, and next-step planning
- if this appears to be a postoperative clinic visit, emphasize interval recovery, symptoms, pathology or imaging discussion, wound status if supported, and follow-up
- assessment should synthesize rather than simply repeat the history
- plan should be practical and succinct
""",
    "consult_note": """
Generate a concise but complete surgical consult note appropriate for an inpatient or ED consultation.

Consult note sections must appear in this order unless a valid placeholder template explicitly rearranges them:
- Reason for Consult
- HPI
- Past Medical History
- Past Surgical History
- Family History
- Social History
- Review of Systems
- Objective
- Assessment and Plan

Formatting requirements:
- use the section header exactly as: Assessment and Plan:
- within Assessment and Plan, first write a short assessment paragraph
- then leave one blank line
- then write the plan as bullet points
- never number the assessment
- never number the plan
- the note should feel clinically complete and demo-worthy, not skeletal
- prefer enough detail that another surgeon could quickly understand the consult question, supporting data, and near-term plan
- Each required consult section header must appear on its own line, with the section content starting on the next line.

HPI requirements:
The HPI must clearly describe the presenting pain/symptoms and should include, when supported or reasonably inferable:
- location
- intensity
- quality
- duration / onset
- exacerbating or alleviating factors
- associated symptoms
- Write the HPI as one continuous paragraph with contiguous sentences.
- Do not insert random line breaks, extra paragraph breaks, or indented fragments within the HPI.

If exacerbating or alleviating factors are not mentioned, state that there are no specific exacerbating or alleviating factors.

If a key HPI pain descriptor is missing, it is acceptable to infer a concise likely descriptor from a strongly supported acute surgical diagnosis. For example, if the source strongly supports acute appendicitis, you may reasonably infer the corresponding pain quality or intensity even if not explicitly stated. Any such inferred HPI wording must be treated as an assumption and wrapped in [[ASSUMPTION]]...[[/ASSUMPTION]].

After the core symptom description, include a brief hospitalization summary when supported by the source material. This may include:
- admission service or care setting
- pertinent lab course
- pertinent imaging findings
- pertinent exam findings
- brief hospital course leading to surgical consultation

Keep this hospitalization summary brief and clinically useful, not repetitive.

History section defaults:
- If Family History is not explicitly mentioned, write: "Non-contributory."
- If Social History is not explicitly mentioned, write: "Denies alcohol use, tobacco use, drug use."
- If Past Medical History is not explicitly mentioned, write a concise neutral statement such as: "None reported."
- If Past Surgical History is not explicitly mentioned, write a concise neutral statement such as: "None reported." or "No prior abdominal surgery reported." when that phrasing is more clinically useful.

Review of Systems requirements:
- Keep ROS lightweight and concise.
- Default to negative/normal systems unless symptoms are specified.
- Reflect the presenting complaint when relevant, but do not create unsupported positives.
- Prefer a one-line ROS summary when the case is straightforward rather than omitting the section entirely.

Objective requirements:
- Must include a physical exam under the "Objective" section.
- Include available vitals, exam findings, labs, and imaging if supported.
- The physical exam should be written in formal exam format with one organ system per line, with the finding on the same line as the label:
  - Gen: ...
  - HEENT: ...
  - Pulmonary: ...
  - Cardiovascular: ...
  - Abdomen: ...
- Never place the finding on a separate line below the organ system label.
- If details are sparse, use the following neutral defaults unless contradicted by the source material:
  - Gen: No acute distress, comfortable
  - HEENT: Normocephalic, atraumatic
  - Pulmonary: Normal work of breathing
  - Cardiovascular: Warm and well perfused
- For the abdominal exam:
  - if abdominal findings are supported, reflect them accurately
  - if no abnormal abdominal findings are provided, default to:
    "Soft, non-tender, non-distended, no guarding, no hernias or masses appreciated"
  - if CT findings support appendicitis, assume focal right lower quadrant tenderness
  - if CT findings support cholecystitis, assume focal right upper quadrant tenderness
- When supported, include concise lab and imaging lines in Objective so the note captures the key workup, not just the exam.
- Prefer compressed clinical formatting such as:
  - Labs: ...
  - Imaging: ...

Assessment and Plan brevity requirements:
- The assessment must be brief: usually 2–3 sentences maximum.
- The plan must be brief: usually 3–6 bullets maximum.
- Prefer compressed clinical language over long explanatory prose.
- Do not restate the same facts already given in the HPI or Objective.
- Do not explain obvious surgical reasoning at length.
- Do not include unnecessary contingency planning unless strongly supported.
- Each plan bullet should usually be a short action phrase, not a full paragraph.
- Similar information density is desired, but with shorter phrasing and less narrative.
- Even when concise, the plan should usually cover disposition/location of care, diet/fluids, antibiotics or other immediate treatment when relevant, symptom control, and operative timing or follow-up recommendations as appropriate to the case.

Consult style rules:
- emphasize the reason for consultation, the key clinical facts, the surgical impression, and actionable recommendations
- avoid filler, repetition, and textbook explanations
- keep the note focused on surgical reasoning and recommendations
""",
}

GLOBAL_RULES = """
Global rules:
- Use only facts supported by the source material and structured case facts.
- Do not invent medications, vital signs, exam findings, imaging results, lab values, PMH, PSH, allergies, or operative details unless reasonably supported by the source material.
- If specific details are missing, omit them or use neutral phrasing rather than fabricate, except where explicit default wording is required by the consult note instructions.
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
- Only include sections that are actually supported by the case facts and useful for the note type, except where the consult note requires specific mandatory sections.
- Do not force rigid templates when the available source material is sparse.
- If data are limited, write a shorter note with fewer details, while still honoring required consult sections.
- If the case supports more detail, expand naturally while staying concise.
- Prefer realistic clinical formatting over completeness for its own sake.
- The note should feel like something a practicing surgeon would actually write in workflow.
"""

STRICT_TEMPLATE_GUIDANCE = """
The user has provided a strict formatting template copied from their EMR or workflow.

Treat the strict template as authoritative for:
- section order
- section labels
- hard formatting expectations
- reusable wording blocks that are meant to recur

If the strict template contains [[EXACT]]...[[/EXACT]] blocks:
- copy the text inside those blocks verbatim when it is clinically compatible with the current case
- do not paraphrase, polish, or partially rewrite that exact text
- if an exact block does not fit the current case, omit it rather than mutating it
- never output the [[EXACT]] or [[/EXACT]] markers themselves
- if a standalone parenthetical instruction immediately precedes an EXACT block, treat it as placement guidance for that exact block
- examples of valid parenthetical directives include:
  - (put this at the bottom)
  - (place under Findings)
  - (use this in Description of Procedure)
- follow those directives when clinically compatible, but never output the parenthetical instruction itself

Use the current case facts to fill in the rest of the note naturally around the strict template.
"""

GUIDANCE_TEMPLATE_GUIDANCE = """
The user has also highlighted surgeon-specific procedural habits, preferred steps, tools, or wording patterns.

If the strict template contains [[GUIDE]]...[[/GUIDE]] blocks:
- treat them as soft procedural guidance, not verbatim text
- recognize the pattern and apply it when clinically compatible with the current case
- preserve the clinical idea, sequence, or idiosyncratic preference even if the final wording changes
- omit the guidance if it is not compatible with the current case
- never output the [[GUIDE]] or [[/GUIDE]] markers themselves
"""

STYLE_EXAMPLE_GUIDANCE = """
The user has also provided a de-identified example note that reflects their preferred style.

Use it as soft guidance for:
- tone
- sentence rhythm
- organization
- level of detail
- surgeon-specific idiosyncrasies

Do not copy stale patient-specific details from the style example.
Strict template instructions override style-example preferences when they conflict.
"""

GLOBAL_TONE_GUIDANCE = """
The user has a global tone profile learned from several de-identified notes.

Use it as high-level cross-note guidance for:
- overall voice
- sentence rhythm
- terseness vs explanation
- favored structure and documentation habits

Apply this tone across note types unless a note-specific format rule conflicts with it.
Do not treat the tone summary as exact wording to copy.
"""


def _compact_case_facts(value):
    if isinstance(value, dict):
        compacted = {
            k: _compact_case_facts(v)
            for k, v in value.items()
        }
        return {
            k: v for k, v in compacted.items()
            if v not in (None, "", [], {})
        }

    if isinstance(value, list):
        compacted = [_compact_case_facts(v) for v in value]
        return [v for v in compacted if v not in (None, "", [], {})]

    return value


def _extract_template_placeholders(template_content: str):
    if not template_content:
        return []
    found = re.findall(r"\{([a-zA-Z0-9_]+)\}", template_content)
    return [p for p in found if p in SUPPORTED_TEMPLATE_PLACEHOLDERS]


def _extract_exact_block_specs(template_content: str):
    if not template_content:
        return []
    matches = re.finditer(
        r"(?:(?:^|\n)\s*\((?P<directive>[^()\n]+)\)\s*\n\s*)?"
        r"\[\[EXACT\]\](?P<block>.*?)\[\[/EXACT\]\]",
        template_content,
        flags=re.IGNORECASE | re.DOTALL,
    )
    specs = []
    for match in matches:
        block = (match.group("block") or "").strip()
        directive = (match.group("directive") or "").strip()
        if not block:
            continue
        specs.append({
            "text": block,
            "placement": directive,
        })
    return specs


def _extract_exact_blocks(template_content: str):
    return [spec["text"] for spec in _extract_exact_block_specs(template_content)]


def _extract_guide_blocks(template_content: str):
    if not template_content:
        return []
    return [
        block.strip()
        for block in re.findall(r"\[\[GUIDE\]\](.*?)\[\[/GUIDE\]\]", template_content, flags=re.IGNORECASE | re.DOTALL)
        if str(block).strip()
    ]


def _strip_exact_markers(template_content: str):
    if not template_content:
        return ""
    cleaned = re.sub(
        r"(^|\n)\s*\([^()\n]+\)\s*(?=\n\s*\[\[EXACT\]\])",
        r"\1",
        template_content,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\[\[/?EXACT\]\]", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\[\[/?GUIDE\]\]", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(
        r"(^|\n)\s*\([^()\n]+\)\s*(?=\n\s*$)",
        r"\1",
        cleaned,
        flags=re.IGNORECASE,
    )
    return cleaned


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
- Use the required consult sections even when the source material is sparse.
- The Assessment and Plan section is the most important part of the note.
- Keep HPI clinically efficient: symptom story first, then brief hospital course with key labs/imaging/exam if available.
- If key pain descriptors are missing, you may infer concise likely wording from a strongly supported acute diagnosis, but tag that wording as [[ASSUMPTION]]...[[/ASSUMPTION]].
- In Objective, use formal exam lines (Gen, HEENT, Pulmonary, Cardiovascular, Abdomen) plus concise Labs/Imaging lines when supported.
- If exam details are sparse, use the neutral defaults from the consult note instructions; if CT supports appendicitis or cholecystitis and no abdominal exam is given, assume focal RLQ or RUQ tenderness respectively, tagged as ASSUMPTION.
- ROS and physical exam content default to ASSUMPTION unless explicitly provided or explicitly stated as normal/negative.
- Assessment should be a short attending-style paragraph synthesizing diagnosis, supporting facts, and operative vs nonoperative reasoning.
- Plan should follow after one blank line as 3-6 hyphen bullets with one actionable item each.
- If the consult is sparse, keep the note concise; if the example note has a distinctive consult structure or recommendation style, match it when appropriate.
- For consult notes, every substantive body-text segment should be tagged as [[FACT]] or [[ASSUMPTION]]. Headings, punctuation, bullet markers, and blank lines may remain untagged.
"""
    return ""


def _build_reasoning_layer(note_type: str) -> str:
    if note_type == "consult_note":
        return """
Before writing the note, internally reason through the following:
1. What is the consult question and most likely surgical issue?
2. Which facts matter most: symptoms, exam, labs, imaging, hospital course?
3. Which history/ROS/objective details are explicit vs assumed?
4. What default history wording is required?
5. What is the clearest concise assessment and near-term plan?

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


def _build_placeholder_mode_guidance(note_type: str, template_content: str) -> str:
    placeholders = _extract_template_placeholders(template_content)
    if not placeholders:
        return ""

    placeholder_list = ", ".join(f"{{{p}}}" for p in placeholders)

    consult_specific = ""
    if note_type == "consult_note":
        consult_specific = """
Special consult placeholder rules:
- {assessment} must contain only the short assessment paragraph.
- {plan} must contain bullet points only, not numbered items.
- {objective} should contain the formal exam and any relevant vitals/labs/imaging summary if appropriate.
- {fh} should default to "Non-contributory." if family history is not given.
- {sh} should default to "Denies alcohol use, tobacco use, drug use." if social history is not given.
"""

    return f"""
The user template contains placeholders and should be treated as a fillable template.

Detected placeholders:
{placeholder_list}

Instructions for placeholder mode:
- Output the final note using the user's template structure as closely as possible.
- Replace each supported placeholder with generated content appropriate to the current case.
- Preserve the template's headings, layout, and overall style whenever safe and appropriate.
- Do not leave supported placeholders unfilled if the section can be generated.
- Do not output braces or placeholder names in the final note.
- If a placeholder section is unsupported by the source material, use neutral/default wording only when allowed by the note rules; otherwise keep the content concise and non-fabricated.
- Do not copy stale or irrelevant content from the example template.

Supported placeholders:
- {{reason_for_consult}}
- {{hpi}}
- {{pmh}}
- {{psh}}
- {{fh}}
- {{sh}}
- {{ros}}
- {{objective}}
- {{assessment}}
- {{plan}}
- {{procedure}}
- {{findings}}
- {{description_of_procedure}}
- {{specimen}}
- {{estimated_blood_loss}}
- {{drains}}
- {{complications}}
- {{disposition}}

{consult_specific}
"""


def _truncate_prompt_value(value, limit):
    value = (value or "").strip()
    if len(value) <= limit:
        return value
    return value[: limit - 3].rstrip() + "..."


def _build_retrieved_examples_guidance(retrieved_examples):
    if not retrieved_examples:
        return ""

    example_lines = []
    for idx, example in enumerate(retrieved_examples[:3], start=1):
        example_lines.append(
            "\n".join([
                f"Example {idx}:",
                f"- Specialty: {example.get('specialty') or 'General Surgery'}",
                f"- Note type: {(example.get('note_type') or '').replace('_', ' ')}",
                f"- Title: {example.get('title') or 'Reviewed example'}",
                f"- Source shorthand: {_truncate_prompt_value(example.get('shorthand_input'), 240)}",
                f"- Gold output excerpt: {_truncate_prompt_value(example.get('corrected_output'), 1100)}",
                f"- Reviewer lessons: {_truncate_prompt_value(example.get('lessons'), 320)}",
            ])
        )

    joined_examples = "\n\n".join(example_lines)
    return f"""
High-confidence reviewed examples from the internal training corpus:
{joined_examples}

Use these examples as style-and-structure guidance only.
- Prefer patterns that match the current specialty and note type.
- Do not copy stale patient details or procedure-specific facts that are not supported by the current case.
- If the retrieved examples conflict with the current case facts, follow the current case facts.
"""


def _build_template_profile_guidance(note_type: str, template_profile):
    if not template_profile:
        return ""

    strict_template_text = (template_profile.get("strict_template_text") or "").strip()
    strict_enabled = bool(template_profile.get("strict_enabled"))
    profile_name = (template_profile.get("name") or "Template profile").strip()

    sections = [f"Active template profile: {profile_name}"]

    if strict_enabled and strict_template_text:
        clean_template = _strip_exact_markers(strict_template_text)
        placeholder_guidance = _build_placeholder_mode_guidance(note_type, clean_template)
        exact_specs = _extract_exact_block_specs(strict_template_text)
        guide_blocks = _extract_guide_blocks(strict_template_text)
        exact_block_section = ""
        if exact_specs:
            joined_blocks = "\n\n".join(
                (
                    f"Exact block {idx}:"
                    + (f"\nPlacement guidance: {spec['placement']}" if spec.get("placement") else "")
                    + f"\n{spec['text']}"
                )
                for idx, spec in enumerate(exact_specs, start=1)
            )
            exact_block_section = f"""
Exact reusable wording blocks that must be copied verbatim when clinically compatible:
{joined_blocks}
"""

        guide_block_section = ""
        if guide_blocks:
            guide_block_section = f"""
{GUIDANCE_TEMPLATE_GUIDANCE}

Surgeon-specific procedural / formatting habits to recognize and apply when compatible:
{chr(10).join(f"- {block}" for block in guide_blocks)}
"""

        sections.append(f"""
{STRICT_TEMPLATE_GUIDANCE}

{placeholder_guidance}

STRICT TEMPLATE:
{clean_template}

{exact_block_section}
{guide_block_section}
""".strip())

    return "\n\n".join(section for section in sections if section)


def _build_global_tone_guidance(global_tone_profile):
    if not global_tone_profile:
        return ""

    summary = (global_tone_profile.get("tone_summary") or "").strip()
    traits = [str(item).strip() for item in (global_tone_profile.get("tone_traits") or []) if str(item).strip()]
    if not summary and not traits:
        return ""

    traits_block = "\n".join(f"- {item}" for item in traits) if traits else "- None provided"
    return f"""
{GLOBAL_TONE_GUIDANCE}

GLOBAL TONE SUMMARY:
{summary}

GLOBAL TONE TRAITS:
{traits_block}
""".strip()


def build_prompt(
    case_facts,
    note_type="op_note",
    template_content=None,
    specialty="General Surgery",
    retrieved_examples=None,
    template_profile=None,
    global_tone_profile=None,
):
    note_type = note_type if note_type in NOTE_TYPE_LABELS else "op_note"
    note_label = NOTE_TYPE_LABELS[note_type]
    note_instructions = NOTE_TYPE_INSTRUCTIONS[note_type]
    note_specific_guidance = _build_note_specific_guidance(note_type)
    reasoning_layer = _build_reasoning_layer(note_type)
    specialty = (specialty or "General Surgery").strip() or "General Surgery"

    compact_case_json = json.dumps(
        _compact_case_facts(case_facts),
        separators=(",", ":"),
        ensure_ascii=True,
    )

    template_section = _build_template_profile_guidance(note_type, template_profile)
    global_tone_section = _build_global_tone_guidance(global_tone_profile)
    if not template_section and template_content:
        placeholder_guidance = _build_placeholder_mode_guidance(note_type, template_content)
        template_section = f"""
{TEMPLATE_GUIDANCE}

{placeholder_guidance}

USER TEMPLATE / EXAMPLE NOTE:
{template_content}
"""

    retrieved_examples_section = _build_retrieved_examples_guidance(retrieved_examples)

    return f"""
You are an expert surgical documentation assistant helping draft high-quality notes for {specialty.lower()}.

Your task is to generate a polished {note_label}.

{note_instructions}

{note_specific_guidance}

{DYNAMIC_FORMATTER_GUIDANCE}

{GLOBAL_RULES}

{reasoning_layer}

Structured case facts and source material:
{compact_case_json}

{retrieved_examples_section}

{global_tone_section}

{template_section}

Final output requirements:
- Produce a complete final {note_label}
- Use polished medical prose and realistic section headings
- Make the note ready for physician review and editing
- Use only the sections supported by the case and useful for the note type, except where consult-note sections are required
- For consult notes, prefer brevity and shorthand-style clinical compression over polished explanatory prose
- For consult notes, include the required [[FACT]]...[[/FACT]] and [[ASSUMPTION]]...[[/ASSUMPTION]] tags in the final output exactly as instructed
- For consult notes, do not omit tagging on substantive body text. If a sentence or clause is not a heading, bullet marker, or blank line, it should be wrapped in either [[FACT]] or [[ASSUMPTION]].
- Append a machine-readable JSON block named ---ASSERTED_FACTS--- containing key assertions (procedure, laterality, estimated_blood_loss, specimen, implants, cpt_codes).
- If asserting an assumption, the sentence must be wrapped in [[ASSUMPTION]]...[[/ASSUMPTION]].
"""


def build_scenario_generation_prompt(
    specialty="General Surgery",
    note_type="consult_note",
    module_label=None,
    module_description=None,
    target_level=1,
    count=3,
    focus=None,
    existing_titles=None,
):
    specialty = (specialty or "General Surgery").strip() or "General Surgery"
    note_type = note_type if note_type in NOTE_TYPE_LABELS else "consult_note"
    note_label = NOTE_TYPE_LABELS[note_type]
    module_label = (module_label or "").strip() or "General Surgery Documentation Module"
    module_description = (module_description or "").strip()
    focus = (focus or "").strip()
    existing_titles = existing_titles or []
    count = max(1, min(int(count or 1), 6))
    target_level = max(1, min(int(target_level or 1), 3))

    existing_block = "\n".join(f"- {title}" for title in existing_titles[:30]) if existing_titles else "- None"
    focus_block = f"\nAdditional focus request: {focus}" if focus else ""

    return f"""
You are designing synthetic training scenarios for a surgical documentation system.

Generate {count} realistic, reviewer-ready scenarios for:
- Specialty: {specialty}
- Note type: {note_label}
- Module: {module_label}
- Target difficulty level: {target_level}{focus_block}

Module goal:
- {module_description or "Create scenarios that train one narrow documentation behavior well."}

The goal is to create scenarios that reveal what the model still needs to learn, not generic trivia.

Rules:
- Make each scenario clinically plausible and specific enough that a surgeon could translate it into shorthand.
- The goal is documentation training, not advanced clinical reasoning or operative decision-making.
- Reviewers should be grading note quality, sectioning, and surgeon-like phrasing, not solving a difficult medical management problem.
- Every scenario should feel like a variation inside the same documentation module, not a jump to a different surgical pattern.
- The scenario_brief must read like a compact chart summary or handoff, not like shorthand.
- The scenario_brief should be formatted as a short structured case packet with labeled blocks, not a single compressed sentence block.
- For consult and clinic scenarios, use these exact labels in the scenario_brief:
  Presentation:
  Workup:
  Current status / surgical question:
- For operative scenarios, use these exact labels in the scenario_brief:
  Indication:
  Intraoperative findings:
  Procedure / disposition:
- Include enough concrete detail that a reviewer can rewrite it into surgeon shorthand without inventing missing facts.
- Prefer 7-11 sentences for consult and clinic scenarios, and 6-9 sentences for operative scenarios.
- Include as many of the following as are relevant: demographics, setting/service, symptom chronology, associated symptoms, pertinent PMH/PSH, key labs, key imaging, focused exam findings, immediate treatments already started, and the exact question being asked of surgery.
- Do not compress the scenario into abbreviations or shorthand.
- Do not use shorthand abbreviations like RLQ, RUQ, SBO, appy, lap appy, robo chole, PMH, PSH, NPO, or abbreviations of that kind inside the scenario_brief unless they are spelled out first.
- Favor high-yield cases and common real-world variations for the specialty.
- Level 1 should be bread-and-butter, straightforward cases with minimal comorbidity and a simple, obvious surgical question.
- Level 2 should add modest ambiguity, one meaningful comorbidity, or a small formatting challenge, but still remain easy to review quickly.
- Level 3 can be somewhat nuanced, but should still stay focused on documentation challenges rather than fellowship-level decision-making.
- Avoid multidisciplinary planning, consent edge cases, ICU-level complexity, dialysis timing questions, and long differential-diagnosis style dilemmas unless explicitly requested.
- Vary diagnoses, operative decisions, and documentation challenges.
- Do not repeat existing scenarios or create near-duplicate titles.
- Do not mention that the scenario is synthetic.
- Keep the scenario focused on facts a surgeon would care about, but make it detailed enough for shorthand translation.
- The learning objectives should be one short sentence focused only on documentation craft.
- The learning objectives should not teach medicine, operative judgment, or residency-level management.

Existing scenario titles to avoid:
{existing_block}

Return valid JSON only as an array of objects.

Each object must contain exactly these keys:
- title
- diagnosis
- procedure_focus
- complexity_level
- question_prompt
- why_now
- scenario_brief
- learning_objectives

The complexity_level must be an integer 1, 2, or 3 matching the requested difficulty.
- question_prompt should be a direct, high-value ask from the system to the reviewer or expert. It should sound like the system is asking for the exact case/note pattern it most needs help with right now.
- why_now should be one short sentence explaining what this scenario will help the model iron out.
"""
