"""MCP server exposing the MatchMiner-AI services as agent tools.

Transports:
  * streamable HTTP at ``/mcp`` on the main web server (``mmai-web serve``)
  * stdio (``mmai-web mcp``) for agents that launch the server themselves

Tool results contain patient data when a tool takes an MRN; only connect
agents that are approved to see it.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import anyio
from mcp.server.mcpserver import MCPServer

from mmai_web.services import get_services
from mmai_web.services.patients import parse_summary
from mmai_web.services.serialize import records

mcp = MCPServer(
    "matchminer-ai",
    instructions=(
        "Clinical trial matching tools (MatchMiner-AI). Typical flow: "
        "match_patient_to_trials(mrn) for the full pipeline, or compose "
        "get_patient_notes -> summarize_patient -> find_candidate_trials -> "
        "score_match_quality / check_exclusion_criteria. Model outputs support, "
        "and do not replace, clinical judgment."
    ),
)


async def _offload[T](fn: Callable[[], T]) -> T:
    """Run blocking model work off the event loop."""
    return await anyio.to_thread.run_sync(fn)


# ---- notes / patients -----------------------------------------------------
@mcp.tool()
async def list_patients() -> list[dict[str, Any]]:
    """List MRNs available from the configured note sources, with note counts."""
    return records(await _offload(lambda: get_services().notes.list_patients()))


@mcp.tool()
async def get_patient_notes(mrn: str, include_text: bool = False) -> dict[str, Any]:
    """Get a patient's clinical notes (id, date, type; text if include_text)."""
    notes = await _offload(lambda: get_services().notes.get_notes(mrn))
    if not include_text:
        notes = notes.drop(columns=["note_text"])
    return {"mrn": mrn, "notes": records(notes)}


@mcp.tool()
async def summarize_patient(mrn: str) -> dict[str, Any]:
    """Summarize a patient's notes into a cancer history summary (age, sex,
    cancer type, histology, extent, biomarkers, treatment history) plus
    evidence for general trial exclusion criteria."""
    s = get_services()
    return await _offload(lambda: s.patients.summarize(s.notes.get_notes(mrn)))


@mcp.tool()
async def extract_patient_journey(mrn: str) -> dict[str, Any]:
    """Extract the dated key events of a patient's cancer journey
    (diagnosis, pathology, biomarkers, surgery, therapy lines, progression),
    each citing the note ids it came from."""
    s = get_services()
    return await _offload(lambda: s.patients.journey(s.notes.get_notes(mrn)))


@mcp.tool()
def parse_patient_summary(summary: str) -> dict[str, Any]:
    """Split a cancer history summary text into fields, biomarkers and
    treatment-history items."""
    return parse_summary(summary)


# ---- trials -----------------------------------------------------------------
@mcp.tool()
def list_trials() -> list[dict[str, Any]]:
    """List trials in the matching corpus with their number of clinical spaces."""
    return get_services().trials.list_trials()


@mcp.tool()
def get_trial(trial_id: str) -> dict[str, Any]:
    """Get a trial's title, summary, eligibility text and its clinical spaces
    (target populations) with general exclusion criteria."""
    return get_services().trials.get_trial(trial_id)


# ---- matching -----------------------------------------------------------------
@mcp.tool()
async def find_candidate_trials(
    cancer_history_summary: str, k: int = 20
) -> list[dict[str, Any]]:
    """Rank trial clinical spaces by semantic similarity (TrialSpace model)
    to a patient's cancer history summary. Returns the top k spaces."""
    found = await _offload(
        lambda: get_services().matching.candidates(
            "patient", cancer_history_summary, k=k
        )
    )
    return records(found)


@mcp.tool()
async def score_match_quality(
    cancer_history_summary: str, space_trial_ids: list[str]
) -> list[dict[str, Any]]:
    """Score how well a patient summary fits each trial clinical space
    (TrialChecker; 0-1, pass at the configured cutoff)."""
    s = get_services()
    spaces = s.trials.space_table()
    pairs = spaces[spaces["space_trial_id"].isin(space_trial_ids)].assign(
        patient_id="patient", cancer_history_summary=cancer_history_summary
    )
    return records(await _offload(lambda: s.matching.score(pairs)))


@mcp.tool()
async def check_exclusion_criteria(
    general_exclusion_criteria_evidence: str, trial_ids: list[str]
) -> list[dict[str, Any]]:
    """Check whether the patient's exclusion-relevant evidence (comorbidities,
    performance status, etc.) passes each trial's general exclusion criteria
    (BoilerplateChecker)."""
    s = get_services()
    trials = (
        s.trials.spaces[s.trials.spaces["trial_id"].isin(trial_ids)]
        .drop_duplicates("trial_id")
        .assign(
            patient_id="patient",
            general_exclusion_criteria_evidence=general_exclusion_criteria_evidence,
        )
    )
    return records(await _offload(lambda: s.matching.exclusion(trials)))


@mcp.tool()
async def embed_texts(texts: list[str]) -> dict[str, Any]:
    """Embed texts with the TrialSpace model (1024-d vectors)."""
    return await _offload(lambda: get_services().embedding.embed(texts))


# ---- pipeline ---------------------------------------------------------------
@mcp.tool()
async def match_patient_to_trials(
    mrn: str, top_k: int = 20, llm_review: bool = False
) -> dict[str, Any]:
    """Run the full MatchMiner-AI pipeline for an MRN and return one decision
    per candidate trial (eligible / needs_review / not_matched) with reasons,
    the patient summary and the key-event journey. Takes minutes; use
    start_trial_matching + get_trial_matching to poll instead."""
    run = await _offload(
        lambda: get_services().pipeline.run_sync(
            mrn, {"top_k": top_k, "llm_review": llm_review}
        )
    )
    out = run.to_dict()
    out["result"].pop("notes", None)  # large; fetch with get_patient_notes
    out["result"].pop("candidates", None)
    return out


@mcp.tool()
def start_trial_matching(
    mrn: str, top_k: int = 20, llm_review: bool = False
) -> dict[str, Any]:
    """Start the full pipeline for an MRN in the background; returns a run id."""
    run = get_services().pipeline.start(mrn, {"top_k": top_k, "llm_review": llm_review})
    return run.to_dict(include_result=False)


@mcp.tool()
def get_trial_matching(run_id: str) -> dict[str, Any]:
    """Get the status, step progress and decisions of a pipeline run."""
    run = get_services().pipeline.get(run_id)
    if run is None:
        raise ValueError(f"Unknown run id {run_id}")
    out = run.to_dict()
    out["result"].pop("notes", None)
    out["result"].pop("candidates", None)
    return out
