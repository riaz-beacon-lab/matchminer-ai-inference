"""System API: /api/health, /api/config"""

from flask import Blueprint, jsonify

from mmai_web.api._common import services

bp = Blueprint("system", __name__, url_prefix="/api")


@bp.get("/health")
def health():
    return jsonify({"ok": True})


@bp.get("/config")
def config():
    """Which model serves which step, and where data comes from."""
    s = services()
    cfg = s.config
    return jsonify(
        {
            "models": {
                "patient_summary": cfg.patient["remote"]["model_name"],
                "trial_summary": cfg.trial["remote"]["model_name"],
                "embedding": cfg.embedding["model_path"],
                "match_quality": cfg.raw["match_quality"]["model_name"],
                "exclusion": cfg.raw["exclusion_criteria"]["model_name"],
                "llm_review": cfg.llm_match_quality["remote"]["model_name"],
            },
            "llm_review_server": cfg.remote.get("server_urls"),
            "apigee_configured": s.openai.configured,
            "notes_sources": [p.name for p in s.settings.notes_sources],
            "score_cutoff": s.matching.score_cutoff,
        }
    )
