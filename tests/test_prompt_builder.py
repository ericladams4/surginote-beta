from parser import build_case_facts
from prompt_builder import build_prompt


def test_consult_prompt_requires_plan_bullets_to_be_explicit_from_shorthand():
    prompt = build_prompt(
        case_facts=build_case_facts(
            "33yo F hx GERD obesity prior c-section here w/ choledocho s/p ERCP 3/17 tbili down to 2.4 from 6. vitals wnl. npo at mn. robo chole tmrw."
        ),
        note_type="consult_note",
    )

    assert "must come only from specific stated plans, actions, or recommendations in the shorthand" in prompt
    assert "Do not convert routine standard-of-care items into plain plan bullets unless the shorthand actually says them." in prompt
    assert "If the shorthand gives only one explicit plan item, it is acceptable for the PLAN section to contain only one bullet." in prompt


def test_consult_prompt_forbids_speculative_or_contingency_plan_bullets():
    prompt = build_prompt(
        case_facts=build_case_facts(
            "33yo F hx GERD obesity prior c-section here w/ choledocho s/p ERCP 3/17 tbili down to 2.4 from 6. vitals wnl. npo at mn. robo chole tmrw."
        ),
        note_type="consult_note",
    )

    assert 'Do not write bullets framed as "if this happens in the OR..." or similar unless that exact contingency is explicitly documented in the source.' in prompt
    assert "Never speculate in the PLAN about what may be needed intraoperatively or after surgery unless explicitly stated in the source." in prompt
    assert 'If further postoperative or disposition details are not explicit, use the exact neutral wording: "Further plans pending operative course."' in prompt
