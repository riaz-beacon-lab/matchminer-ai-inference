"""Unit tests for logic that does not need models or network."""

from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
from matchminer_ai.llm.prompt_rendering import Prompt

from mmai_web.llm.backends import (
    OPENAI_RESPONSES,
    OpenAIResponsesBackend,
    RoutingBackend,
)
from mmai_web.services.notes import normalize_notes
from mmai_web.services.patients import parse_summary
from mmai_web.services.pipeline import ELIGIBLE, NOT_MATCHED, REVIEW, decide

SUMMARY = """Age: 71
Sex: Female
Cancer type: Glioblastoma
Histology: IDH-wildtype, WHO Grade 4
Current extent: Progressive
Biomarkers: MGMT promoter unmethylated, PDGFRA amplification (copy number approximately 8), NA
Treatment history:
# 1/2020: Maximal surgical debulking
# 10/2020-7/2021: Adjuvant temozolomide; achieved partial response
"""


def test_parse_summary_fields_biomarkers_treatments():
    parsed = parse_summary(SUMMARY)
    assert parsed["fields"]["Cancer type"] == "Glioblastoma"
    assert parsed["fields"]["Age"] == "71"
    assert parsed["biomarkers"] == [
        "MGMT promoter unmethylated",
        "PDGFRA amplification (copy number approximately 8)",
    ]
    assert parsed["treatment_history"] == [
        {"when": "1/2020", "what": "Maximal surgical debulking"},
        {
            "when": "10/2020-7/2021",
            "what": "Adjuvant temozolomide; achieved partial response",
        },
    ]


def test_normalize_notes_drops_broken_rows_and_assigns_ids():
    raw = pd.DataFrame(
        {
            "mrn": ["1", "1", "1", "2"],
            "note_text": ["b", "a", None, "c"],
            "note_date": ["2024-02-01", "2024-01-01", "2024-01-05", "not a date"],
            "Unnamed: 5": [None, None, None, None],
        }
    )
    notes = normalize_notes(raw)
    assert notes["note_text"].tolist() == ["a", "b"]
    assert notes["note_id"].tolist() == ["N0001", "N0002"]
    assert set(notes["event_type"]) == {"Note"}


def test_decide_rules():
    base = {"match_quality_score": 0.8, "exclusion_criteria_pass": True}
    assert decide(pd.Series(base), 0.2)[0] == ELIGIBLE
    assert (
        decide(pd.Series({**base, "match_quality_score": 0.1}), 0.2)[0] == NOT_MATCHED
    )
    assert (
        decide(pd.Series({**base, "exclusion_criteria_pass": False}), 0.2)[0] == REVIEW
    )
    assert decide(pd.Series({**base, "llm_match_quality_score": 0}), 0.2)[0] == REVIEW
    assert decide(pd.Series({**base, "llm_match_quality_score": 2}), 0.2)[0] == ELIGIBLE
    assert (
        decide(pd.Series({**base, "llm_exclusion_criteria_pass": False}), 0.2)[0]
        == REVIEW
    )
    # A failed / unparsed review (-1) leaves the classifier decision in place.
    decision, reasons = decide(pd.Series({**base, "llm_match_quality_score": -1}), 0.2)
    assert decision == ELIGIBLE
    assert "LLM review failed or could not be parsed" in reasons


class FakeOpenAI:
    def __init__(self):
        self.calls = []

    def respond(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            status="completed",
            output_text=f"answer:{kwargs['messages'][-1]['content']}",
            output=[],
        )


class FakeDefault:
    def __init__(self):
        self.called = False

    def generate_llm_outputs(self, **kwargs):
        self.called = True
        return "default"


def test_routing_backend_sends_provider_tasks_to_responses_in_order():
    fake = FakeOpenAI()
    default = FakeDefault()
    router = RoutingBackend(default, OpenAIResponsesBackend(fake))
    prompts = [
        Prompt(
            row_idx=i,
            prompt_text="",
            max_tokens=100,
            messages=[{"role": "user", "content": str(i)}],
        )
        for i in (1, 0)
    ]
    llm_config = {
        "provider": OPENAI_RESPONSES,
        "model_name": "gpt-5.6-luna",
        "remote": {"reasoning_effort": "low", "max_concurrency": 2},
    }
    result = router.generate_llm_outputs(prompt_list=prompts, llm_config=llm_config)
    assert result.final_outputs == ["answer:0", "answer:1"]
    assert result.finish_reasons == ["stop", "stop"]
    assert {c["model"] for c in fake.calls} == {"gpt-5.6-luna"}
    assert not default.called

    assert router.generate_llm_outputs(prompt_list=prompts, llm_config={}) == "default"
