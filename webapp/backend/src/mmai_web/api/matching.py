"""Embedding + matching API: /api/embedding, /api/matching"""

from flask import Blueprint, jsonify

from mmai_web.api._common import body, frame, require, services
from mmai_web.services.serialize import records

embedding_bp = Blueprint("embedding", __name__, url_prefix="/api/embedding")
bp = Blueprint("matching", __name__, url_prefix="/api/matching")

QUALITY_COLUMNS = [
    "patient_id",
    "space_trial_id",
    "cancer_history_summary",
    "clinical_space_summary",
]
EXCLUSION_COLUMNS = [
    "patient_id",
    "trial_id",
    "general_exclusion_criteria",
    "general_exclusion_criteria_evidence",
]


@embedding_bp.post("")
def embed():
    """TrialSpace embeddings. Body: ``{"texts": ["...", ...]}``"""
    data = body()
    require(data, "texts")
    return jsonify(services().embedding.embed([str(t) for t in data["texts"]]))


@bp.post("/candidates")
def candidates():
    """Top-k trial spaces for a patient summary.

    Body: ``{"cancer_history_summary": "...", "patient_id": "p", "k": 20}``
    """
    data = body()
    require(data, "cancer_history_summary")
    found = services().matching.candidates(
        str(data.get("patient_id", "patient")),
        str(data["cancer_history_summary"]),
        k=int(data.get("k", 20)),
    )
    return jsonify(records(found))


@bp.post("/quality")
def quality():
    """TrialChecker. Body: ``{"pairs": [{patient_id, space_trial_id,
    cancer_history_summary, clinical_space_summary}]}``"""
    pairs = frame(body().get("pairs"), "pairs", QUALITY_COLUMNS)
    return jsonify(records(services().matching.score(pairs)))


@bp.post("/exclusion")
def exclusion():
    """BoilerplateChecker. Body: ``{"pairs": [{patient_id, trial_id,
    general_exclusion_criteria, general_exclusion_criteria_evidence}]}``"""
    pairs = frame(body().get("pairs"), "pairs", EXCLUSION_COLUMNS)
    return jsonify(records(services().matching.exclusion(pairs)))


@bp.post("/llm-review")
def llm_review():
    """Local-LLM 0-5 score + exclusion verdict, with rationale text.

    Pairs need the union of the quality and exclusion columns.
    """
    pairs = frame(
        body().get("pairs"),
        "pairs",
        sorted(set(QUALITY_COLUMNS) | set(EXCLUSION_COLUMNS)),
    )
    return jsonify(records(services().matching.llm_review(pairs)))
