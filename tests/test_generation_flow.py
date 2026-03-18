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
