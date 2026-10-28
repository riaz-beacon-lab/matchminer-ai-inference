"""Helpers shared by the API blueprints."""

from __future__ import annotations

from typing import Any

import pandas as pd
from flask import abort, request

from mmai_web.services import Services, get_services
from mmai_web.services.notes import normalize_notes


def services() -> Services:
    return get_services()


def body() -> dict[str, Any]:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, description="Expected a JSON object body")
    return data


def require(data: dict[str, Any], *keys: str) -> None:
    missing = [k for k in keys if data.get(k) in (None, "", [])]
    if missing:
        abort(400, description=f"Missing field(s): {', '.join(missing)}")


def frame(rows: Any, name: str, columns: list[str]) -> pd.DataFrame:
    if not isinstance(rows, list) or not rows:
        abort(400, description=f"'{name}' must be a non-empty list of objects")
    df = pd.DataFrame(rows)
    missing = [c for c in columns if c not in df.columns]
    if missing:
        abort(400, description=f"'{name}' rows are missing: {', '.join(missing)}")
    return df


def notes_from_body(data: dict[str, Any]) -> pd.DataFrame:
    """Notes either looked up by ``mrn`` or supplied inline as ``notes``."""
    if data.get("notes"):
        raw = frame(data["notes"], "notes", ["note_text", "note_date"])
        if "patient_id" not in raw.columns and "mrn" not in raw.columns:
            raw["patient_id"] = str(data.get("mrn") or "patient")
        notes = normalize_notes(raw)
        notes["note_id"] = [f"N{i + 1:04d}" for i in range(len(notes))]
        return notes
    require(data, "mrn")
    return services().notes.get_notes(str(data["mrn"]))
