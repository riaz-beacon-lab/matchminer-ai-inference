"""Trials API: /api/trials"""

from flask import Blueprint, jsonify

from mmai_web.api._common import body, frame, services

bp = Blueprint("trials", __name__, url_prefix="/api/trials")


@bp.get("")
def list_trials():
    return jsonify(services().trials.list_trials())


@bp.get("/<trial_id>")
def get_trial(trial_id: str):
    """Trial info plus its clinical spaces and general exclusion criteria."""
    return jsonify(services().trials.get_trial(trial_id))


@bp.post("/summarize")
def summarize():
    """Extract clinical spaces for new trials (summary LLM).

    Body: ``{"trials": [{trial_id, trial_title, brief_summary,
    eligibility_criteria}], "add_to_corpus": false}``
    """
    data = body()
    trials = frame(
        data.get("trials"),
        "trials",
        ["trial_id", "trial_title", "brief_summary", "eligibility_criteria"],
    )
    return jsonify(
        services().trials.summarize(
            trials, add_to_corpus=bool(data.get("add_to_corpus"))
        )
    )
