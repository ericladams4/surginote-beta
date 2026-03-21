import app as surginote_app
from parser import build_case_facts


def test_build_case_facts_basic():
    facts = build_case_facts("lap chole for symptomatic gallstones, uncomplicated, ebl minimal")
    assert facts.get("procedure") or facts.get("clinical_context")


def test_two_stage_generate_sanitized_example(monkeypatch):
    def fake_call_model_and_log(prompt, **kwargs):
        return (
            "Procedure performed without complication.\n"
            "---ASSERTED_FACTS---\n"
            "{\"procedure\":\"laparoscopic_cholecystectomy\",\"laterality\":\"\",\"estimated_blood_loss\":\"minimal\",\"specimen\":\"gallbladder\"}\n"
            "---END_ASSERTED_FACTS---",
            {"total_tokens": 123},
        )

    monkeypatch.setattr(surginote_app, "call_model_and_log", fake_call_model_and_log)

    draft_text, meta = surginote_app.two_stage_generate(
        "lap chole for symptomatic gallstones, ebl minimal, specimen gallbladder",
        note_type="op_note",
    )

    assert isinstance(draft_text, str)
    assert draft_text
    assert isinstance(meta, dict)
    assert meta["usage"]["total_tokens"] == 123
    assert isinstance(meta["asserted_from_model"], dict)


def test_build_case_facts_does_not_confuse_sob_with_sbo_or_invent_ast():
    facts = build_case_facts(
        "74 yo M hx tobacco use and ETOH use, has not seen a doctor in 20 yrs, here w/ worsening SOB x 2 years but worse in last 2 months. "
        "Reports significant orthopnea and leg swelling. Decrease oral intake. Denies chest pain. Looks cachectic. Needs 4L O2 to sat well in ED. "
        "No O2 at home. CT PE negative for PE but c/f 2.2cm RUL nodule c/f malignancy. Pt admitted to medicine. thoracic surgery consulted. "
        "Agree with medicine w/u for CHF exacerbation but fear this is advanced malignancy. Will tentativley plan for diagnostic endobronchial ultrasound on Monday. "
        "NPO at midnight."
    )

    normalized = facts.get("normalized_input", "").lower()
    clinical = facts.get("clinical_context", {})
    labs = clinical.get("labs", {})
    pmh = str(clinical.get("past_medical_history") or "").lower()

    assert "shortness of breath" in normalized
    assert "small bowel obstruction" not in normalized
    assert "small bowel obstruction" not in pmh
    assert "ast" not in labs
    assert "abdominal_pain" not in clinical.get("symptoms", [])
    assert clinical.get("social_history") == "Alcohol use, Tobacco use."


def test_case_primary_diagnosis_supports_pulmonary_nodule_consult():
    facts = build_case_facts(
        "74 yo M here w/ worsening SOB. CT PE negative for PE but c/f 2.2cm RUL nodule c/f malignancy. "
        "thoracic surgery consulted. tentative diagnostic endobronchial ultrasound Monday."
    )

    diagnosis = surginote_app._case_primary_diagnosis(facts)
    assert "nodule" in diagnosis.lower()


def test_two_stage_generate_allows_consult_without_canonical_general_surgery_procedure(monkeypatch):
    def fake_call_model_and_log(prompt, **kwargs):
        return (
            "Reason for Consult:\nThoracic surgery evaluation.\n"
            "---ASSERTED_FACTS---\n"
            "{\"procedure\":\"\",\"diagnosis\":\"pulmonary nodule concerning for malignancy\"}\n"
            "---END_ASSERTED_FACTS---",
            {"total_tokens": 123},
        )

    monkeypatch.setattr(surginote_app, "call_model_and_log", fake_call_model_and_log)

    draft_text, meta = surginote_app.two_stage_generate(
        "74 yo M hx tobacco use and ETOH use, worsening SOB. CT PE negative for PE but c/f 2.2cm RUL nodule c/f malignancy. thoracic surgery consulted. EBUS Monday. NPO at midnight.",
        note_type="consult_note",
    )

    assert "Thoracic surgery evaluation" in draft_text
    assert meta["usage"]["total_tokens"] == 123


def test_build_case_facts_infers_thoracic_specialty():
    facts = build_case_facts(
        "72 yo M worsening SOB, CT PE negative but 2.1 cm right upper lobe pulmonary nodule concerning for malignancy. "
        "Thoracic surgery consulted. EBUS Monday. NPO at midnight."
    )

    assert facts.get("specialty_hint") == "Thoracic Surgery"
    assert "bronchoscopy" in (facts.get("clinical_context", {}).get("plan_signals") or [])


def test_build_case_facts_infers_vascular_specialty():
    facts = build_case_facts(
        "68 yo F w rest pain and chronic limb threatening ischemia, CTA shows femoral occlusion. "
        "vascular surgery consulted. heparin started. arterial duplex pending."
    )

    assert facts.get("specialty_hint") == "Vascular Surgery"
    assert "heparin" in (facts.get("clinical_context", {}).get("plan_signals") or [])


def test_build_case_facts_infers_trauma_specialty():
    facts = build_case_facts(
        "34 yo M after MVC with rib fractures and pneumothorax. trauma surgery consulted. chest tube placed."
    )

    assert facts.get("specialty_hint") == "Trauma / Acute Care Surgery"
    assert "chest_tube" in (facts.get("clinical_context", {}).get("plan_signals") or [])


def test_effective_generation_specialty_uses_inferred_specialty_when_request_is_default():
    facts = build_case_facts(
        "72 yo M worsening SOB, lung nodule concerning for malignancy. thoracic surgery consulted. EBUS Monday."
    )

    assert surginote_app._effective_generation_specialty("General Surgery", facts) == "Thoracic Surgery"
