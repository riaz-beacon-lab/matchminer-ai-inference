"""Pipeline API: /api/pipeline  (MRN -> final trial decisions)"""

from flask import Blueprint, abort, jsonify

from mmai_web.api._common import body, require, services

bp = Blueprint("pipeline", __name__, url_prefix="/api/pipeline")


@bp.post("/runs")
def start_run():
    """Start a run. Body: ``{"mrn": "...", "options": {top_k, llm_review,
    llm_review_top_n, include_journey}}``. Returns 202 with the run id."""
    data = body()
    require(data, "mrn")
    run = services().pipeline.start(str(data["mrn"]), data.get("options"))
    return jsonify(run.to_dict(include_result=False)), 202


@bp.get("/runs")
def list_runs():
    runs = services().pipeline.list()
    return jsonify([r.to_dict(include_result=False) for r in runs])


@bp.get("/runs/<run_id>")
def get_run(run_id: str):
    """Status, per-step progress and (partial) results."""
    run = services().pipeline.get(run_id)
    if run is None:
        abort(404, description="Unknown run id")
    return jsonify(run.to_dict())
