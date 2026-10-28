"""Notes service: clinical notes for an MRN.

Notes are read from CSV exports with (at least) ``patient_id``/``mrn``,
``note_text`` and ``note_date`` columns; ``event_type`` and ``note_id`` are
optional. ``patient_id`` is treated as the MRN. Other sources (for example the
mc-gdm Data Mart MCP server) can be added by implementing ``NotesProvider``.

Patient data stays in memory; nothing here writes notes to disk or logs.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Protocol

import pandas as pd

logger = logging.getLogger(__name__)

NOTE_COLUMNS = ["note_id", "patient_id", "note_date", "event_type", "note_text"]


class NotesProvider(Protocol):
    def list_patients(self) -> pd.DataFrame: ...

    def get_notes(self, mrn: str) -> pd.DataFrame: ...


def normalize_notes(raw: pd.DataFrame, *, source: str = "input") -> pd.DataFrame:
    """Coerce a note table to NOTE_COLUMNS and drop unusable rows."""
    notes = raw.rename(columns={"mrn": "patient_id", "MRN": "patient_id"}).copy()
    missing = {"patient_id", "note_text", "note_date"} - set(notes.columns)
    if missing:
        raise ValueError(f"{source}: missing note columns {sorted(missing)}")

    valid = notes["note_text"].notna() & notes["patient_id"].notna()
    # Rows broken by unescaped quotes/newlines in CSV exports spill text into
    # trailing "Unnamed: N" columns; drop them (same rule as run_mayo_local).
    unnamed = notes.filter(like="Unnamed")
    if not unnamed.empty:
        valid &= unnamed.isna().all(axis=1)
    notes = notes[valid].copy()

    notes["patient_id"] = notes["patient_id"].astype(str).str.strip()
    notes["note_date"] = pd.to_datetime(notes["note_date"], errors="coerce")
    notes = notes[notes["note_date"].notna()]
    if "event_type" not in notes.columns:
        notes["event_type"] = "Note"
    notes["event_type"] = notes["event_type"].fillna("Note").astype(str)
    if "note_id" not in notes.columns:
        notes["note_id"] = None
    notes = notes.sort_values(["patient_id", "note_date"]).reset_index(drop=True)
    fallback_ids = notes.groupby("patient_id").cumcount().map(lambda i: f"N{i + 1:04d}")
    notes["note_id"] = notes["note_id"].fillna(fallback_ids).astype(str)
    return notes[NOTE_COLUMNS]


class CsvNotesProvider:
    """Notes from one or more CSV files, loaded lazily and kept in memory."""

    def __init__(self, sources: list[Path]) -> None:
        self._sources = sources
        self._notes: pd.DataFrame | None = None
        self._lock = threading.Lock()

    def _load(self) -> pd.DataFrame:
        with self._lock:
            if self._notes is None:
                frames = []
                for path in self._sources:
                    raw = pd.read_csv(path, dtype=str)
                    frame = normalize_notes(raw, source=path.name)
                    logger.info("Loaded %d notes from %s", len(frame), path.name)
                    frames.append(frame)
                notes = pd.concat(frames, ignore_index=True)
                # The same note can appear in several exports (e.g. serial
                # note sets); keep one copy.
                self._notes = notes.drop_duplicates(
                    subset=["patient_id", "note_date", "note_text"]
                ).reset_index(drop=True)
            return self._notes

    def list_patients(self) -> pd.DataFrame:
        notes = self._load()
        return (
            notes.groupby("patient_id")
            .agg(
                n_notes=("note_text", "size"),
                first_date=("note_date", "min"),
                last_date=("note_date", "max"),
            )
            .reset_index()
            .rename(columns={"patient_id": "mrn"})
        )

    def get_notes(self, mrn: str) -> pd.DataFrame:
        notes = self._load()
        selected = notes[notes["patient_id"] == str(mrn).strip()].copy()
        # Re-number per patient after cross-file de-duplication.
        selected["note_id"] = [f"N{i + 1:04d}" for i in range(len(selected))]
        return selected.reset_index(drop=True)


class PatientNotFound(LookupError):
    pass


class NotesService:
    def __init__(self, provider: NotesProvider) -> None:
        self.provider = provider

    def list_patients(self) -> pd.DataFrame:
        return self.provider.list_patients()

    def get_notes(self, mrn: str) -> pd.DataFrame:
        notes = self.provider.get_notes(mrn)
        if notes.empty:
            raise PatientNotFound(f"No notes found for MRN {mrn!r}")
        return notes
