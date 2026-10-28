"""Patients API: /api/patients

Body for summary/journey: ``{"mrn": "..."}`` or ``{"notes": [{note_text,
note_date, event_type?, patient_id?}, ...]}`` (inline notes, so other apps that
hold their own data can reuse the service).
"""

from flask import Blueprint, jsonify

from mmai_web.api._common import body, notes_from_body, require, services
from mmai_web.services.patients import parse_summary

bp = Blueprint("patients", __name__, url_prefix="/api/patients")


@bp.post("/summary")
def summarize():
    """Cancer history summary + exclusion evidence (summary LLM)."""
    return jsonify(services().patients.summarize(notes_from_body(body())))


@bp.post("/journey")
def journey():
    """Dated key events of the cancer journey, each citing note ids."""
    return jsonify(services().patients.journey(notes_from_body(body())))


@bp.post("/parse-summary")
def parse():
    """Split an existing summary text into fields / biomarkers / treatments."""
    data = body()
    require(data, "summary")
    return jsonify(parse_summary(str(data["summary"])))
