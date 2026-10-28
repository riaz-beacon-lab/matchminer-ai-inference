"""Notes API: /api/notes"""

from flask import Blueprint, jsonify, request

from mmai_web.api._common import services
from mmai_web.services.serialize import records

bp = Blueprint("notes", __name__, url_prefix="/api/notes")


@bp.get("/patients")
def list_patients():
    """Patients (MRNs) available from the configured note sources."""
    return jsonify(records(services().notes.list_patients()))


@bp.get("/patients/<mrn>")
def get_notes(mrn: str):
    """Notes for one MRN. ``?text=0`` omits note text (metadata only)."""
    notes = services().notes.get_notes(mrn)
    if request.args.get("text") == "0":
        notes = notes.drop(columns=["note_text"])
    return jsonify({"mrn": mrn, "notes": records(notes)})
