"""Patient service: summaries (via matchminer-ai) and a key-event journey."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import pandas as pd
from matchminer_ai.config import MMAIConfig
from matchminer_ai.patients import summarize_patients

from mmai_web.llm.apigee import ApigeeOpenAI

logger = logging.getLogger(__name__)

# Summary headings emitted by patient.serial.user.question.txt.
SUMMARY_FIELDS = [
    "Age",
    "Sex",
    "Cancer type",
    "Histology",
    "Current extent",
    "Biomarkers",
    "Treatment history",
]

_FIELD_RE = re.compile(
    r"^\s*(" + "|".join(re.escape(f) for f in SUMMARY_FIELDS) + r")\s*:\s*(.*)$",
    re.IGNORECASE,
)
_TREATMENT_RE = re.compile(r"^\s*(?:#|-|\*|\d+\.)\s*(.+)$")


def parse_summary(text: str) -> dict[str, Any]:
    """Split a cancer history summary into its labelled fields.

    ``treatment_history`` items are ``{"when": ..., "what": ...}`` parsed from
    lines like ``# 10/2020-7/2021: Adjuvant temozolomide``.
    """
    fields: dict[str, str] = {}
    treatments: list[dict[str, str]] = []
    current: str | None = None
    for line in (text or "").splitlines():
        match = _FIELD_RE.match(line)
        if match:
            current = next(f for f in SUMMARY_FIELDS if f.lower() == match[1].lower())
            fields[current] = match[2].strip()
            continue
        if current == "Treatment history":
            item = _TREATMENT_RE.match(line)
            if item:
                when, sep, what = item[1].partition(": ")
                treatments.append(
                    {"when": when.strip(), "what": what.strip()}
                    if sep
                    else {"when": "", "what": item[1].strip()}
                )
        elif current and line.strip():
            fields[current] = f"{fields[current]} {line.strip()}".strip()
    if not treatments and fields.get("Treatment history"):
        treatments.append({"when": "", "what": fields["Treatment history"]})
    biomarkers = [
        b.strip()
        for b in re.split(r"[,;](?![^()]*\))", fields.get("Biomarkers", ""))
        if b.strip() and b.strip().upper() != "NA"
    ]
    return {
        "fields": {f: fields.get(f, "") for f in SUMMARY_FIELDS},
        "biomarkers": biomarkers,
        "treatment_history": treatments,
    }


JOURNEY_CATEGORIES = [
    "presentation",
    "diagnosis",
    "pathology",
    "biomarker",
    "imaging",
    "surgery",
    "systemic_therapy",
    "radiation",
    "response",
    "progression",
    "toxicity",
    "other",
]

JOURNEY_SCHEMA: dict[str, Any] = {
    "title": "patient_journey",
    "type": "object",
    "properties": {
        "events": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "YYYY-MM-DD, YYYY-MM or YYYY",
                    },
                    "category": {"type": "string", "enum": JOURNEY_CATEGORIES},
                    "title": {"type": "string", "description": "<= 8 words"},
                    "detail": {"type": "string", "description": "1-2 sentences"},
                    "note_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["date", "category", "title", "detail", "note_ids"],
                "additionalProperties": False,
            },
        },
        "headline": {
            "type": "string",
            "description": "One-sentence oncologic headline for the patient",
        },
    },
    "required": ["events", "headline"],
    "additionalProperties": False,
}

JOURNEY_INSTRUCTIONS = """You are an oncology clinical abstractor. From the \
patient's clinical notes, extract the key events of the patient's cancer \
journey in chronological order: initial presentation, diagnosis, pathology, \
biomarker/genomic results, key imaging findings, surgeries, systemic \
therapies (each line of therapy as one event, with start date), radiation, \
responses, progressions, and clinically significant toxicities. Merge \
duplicates that several notes describe. Use the most precise date the notes \
support. Every event must cite the note_ids it came from. Do not invent \
facts that the notes do not state."""


def _notes_prompt(notes: pd.DataFrame) -> str:
    blocks = [
        f"<note id={row.note_id} date={row.note_date:%Y-%m-%d} type={row.event_type}>\n"
        f"{row.note_text}\n</note>"
        for row in notes.itertuples()
    ]
    return "\n\n".join(blocks)


def _batches(notes: pd.DataFrame, max_chars: int) -> list[pd.DataFrame]:
    batches: list[pd.DataFrame] = []
    start, size = 0, 0
    for i, text in enumerate(notes["note_text"].astype(str)):
        if size and size + len(text) > max_chars:
            batches.append(notes.iloc[start:i])
            start, size = i, 0
        size += len(text)
    batches.append(notes.iloc[start:])
    return [b for b in batches if not b.empty]


class PatientService:
    def __init__(
        self,
        config: MMAIConfig,
        openai: ApigeeOpenAI,
        *,
        journey_max_chars: int = 600_000,
    ) -> None:
        self.config = config
        self.openai = openai
        self.journey_max_chars = journey_max_chars

    @property
    def summary_model(self) -> str:
        return str(self.config.patient["remote"]["model_name"])

    def summarize(self, notes: pd.DataFrame) -> dict[str, Any]:
        """Run the package's serial patient summarization for one patient."""
        patient_ids = notes["patient_id"].astype(str).unique()
        if len(patient_ids) != 1:
            raise ValueError("summarize expects notes for exactly one patient")
        summaries, qc = summarize_patients(
            notes[["patient_id", "note_text", "note_date"]],
            config=self.config,
            return_qc=True,
        )
        qc_records = json.loads(qc.to_json(orient="records"))
        if summaries.empty:
            return {
                "patient_id": patient_ids[0],
                "cancer_history_summary": "",
                "general_exclusion_criteria_evidence": "",
                "parsed": parse_summary(""),
                "qc": qc_records,
                "ok": False,
            }
        row = summaries.iloc[0]
        return {
            "patient_id": str(row["patient_id"]),
            "cancer_history_summary": str(row["cancer_history_summary"]),
            "general_exclusion_criteria_evidence": str(
                row["general_exclusion_criteria_evidence"]
            ),
            "parsed": parse_summary(str(row["cancer_history_summary"])),
            "qc": qc_records,
            "ok": True,
        }

    def journey(self, notes: pd.DataFrame) -> dict[str, Any]:
        """Extract dated key events with note citations, for the flowchart."""
        events: list[dict[str, Any]] = []
        headline = ""
        valid_ids = set(notes["note_id"])
        for batch in _batches(notes, self.journey_max_chars):
            response = self.openai.respond(
                model=self.summary_model,
                messages=[
                    {"role": "system", "content": JOURNEY_INSTRUCTIONS},
                    {"role": "user", "content": _notes_prompt(batch)},
                ],
                max_output_tokens=16000,
                reasoning_effort="low",
                json_schema=JOURNEY_SCHEMA,
            )
            if response.status != "completed":
                logger.warning("Journey extraction returned %s", response.status)
                continue
            payload = json.loads(response.output_text)
            headline = payload.get("headline") or headline
            events.extend(payload.get("events", []))

        seen: set[tuple[str, str]] = set()
        merged = []
        for event in sorted(events, key=lambda e: e.get("date", "")):
            key = (event.get("date", ""), event.get("title", "").lower())
            if key in seen:
                continue
            seen.add(key)
            event["note_ids"] = [n for n in event.get("note_ids", []) if n in valid_ids]
            event["id"] = f"E{len(merged) + 1:03d}"
            merged.append(event)
        return {"headline": headline, "events": merged}
