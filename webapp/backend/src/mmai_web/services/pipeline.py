"""MRN -> trial decisions: the end-to-end MatchMiner-AI pipeline as a job.

Steps (each reported with status/timing so the UI can draw progress):

1. notes       load the patient's notes
2. summary     serial patient summarization (summary LLM)
3. journey     dated key events with note citations (summary LLM)
4. retrieve    TrialSpace embedding + top-k trial spaces
5. quality     TrialChecker score for every candidate space
6. exclusion   BoilerplateChecker for every candidate trial
7. review      optional local-LLM rationale for the top trials
8. decide      one decision per trial

Results are held in memory only (they contain patient data).
"""

from __future__ import annotations

import logging
import threading
import time
import traceback
import uuid
from collections import OrderedDict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from mmai_web.services.matching import MatchingService
from mmai_web.services.notes import NotesService
from mmai_web.services.patients import PatientService
from mmai_web.services.serialize import records

logger = logging.getLogger(__name__)

STEPS = [
    ("notes", "Load notes"),
    ("summary", "Summarize patient"),
    ("journey", "Extract key events"),
    ("retrieve", "Retrieve candidate trial spaces"),
    ("quality", "Score match quality (TrialChecker)"),
    ("exclusion", "Check general exclusions (BoilerplateChecker)"),
    ("review", "LLM review (local Gemma)"),
    ("decide", "Final decision"),
]

ELIGIBLE = "eligible"
REVIEW = "needs_review"
NOT_MATCHED = "not_matched"


@dataclass
class RunOptions:
    top_k: int = 20
    llm_review: bool = False
    llm_review_top_n: int = 3
    include_journey: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> RunOptions:
        data = data or {}
        return cls(
            top_k=int(data.get("top_k", cls.top_k)),
            llm_review=bool(data.get("llm_review", cls.llm_review)),
            llm_review_top_n=int(data.get("llm_review_top_n", cls.llm_review_top_n)),
            include_journey=bool(data.get("include_journey", cls.include_journey)),
        )


@dataclass
class Run:
    id: str
    mrn: str
    options: RunOptions
    status: str = "queued"  # queued | running | done | error
    created_at: float = field(default_factory=time.time)
    steps: list[dict[str, Any]] = field(
        default_factory=lambda: [
            {"key": k, "label": label, "status": "pending"} for k, label in STEPS
        ]
    )
    result: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def step(self, key: str) -> dict[str, Any]:
        return next(s for s in self.steps if s["key"] == key)

    def to_dict(self, *, include_result: bool = True) -> dict[str, Any]:
        out = {
            "id": self.id,
            "mrn": self.mrn,
            "status": self.status,
            "created_at": self.created_at,
            "options": self.options.__dict__,
            "steps": self.steps,
            "error": self.error,
        }
        if include_result:
            out["result"] = self.result
        return out


def decide(row: pd.Series, cutoff: float) -> tuple[str, list[str]]:
    """Rule combining the two classifier checks (and the LLM review if run)."""
    reasons = []
    quality_ok = row["match_quality_score"] >= cutoff
    reasons.append(
        f"TrialChecker {row['match_quality_score']:.2f} "
        f"{'>=' if quality_ok else '<'} cutoff {cutoff:.2f}"
    )
    if not quality_ok:
        return NOT_MATCHED, reasons
    exclusion_ok = bool(row.get("exclusion_criteria_pass", True))
    reasons.append(
        "passes general exclusion criteria"
        if exclusion_ok
        else "possible general exclusion (BoilerplateChecker)"
    )
    # LLM review (optional). Its 0-5 score adds specificity points on top of
    # "reasonable"; only 0 ("not a reasonable consideration") is a red flag.
    llm_flags = False
    llm_excl = row.get("llm_exclusion_criteria_pass")
    if llm_excl is False:
        reasons.append("LLM reviewer flags an exclusion")
        llm_flags = True
    llm_score = row.get("llm_match_quality_score")
    if llm_score is not None and pd.notna(llm_score):
        if float(llm_score) < 0:
            # The package reports -1 when the answer could not be parsed
            # (including failed requests); the classifier decision stands.
            reasons.append("LLM review failed or could not be parsed")
        else:
            reasons.append(f"LLM reviewer score {int(llm_score)}/5")
            llm_flags |= float(llm_score) == 0
    if exclusion_ok and not llm_flags:
        return ELIGIBLE, reasons
    return REVIEW, reasons


class PipelineService:
    def __init__(
        self,
        notes: NotesService,
        patients: PatientService,
        matching: MatchingService,
        *,
        max_runs: int = 50,
    ) -> None:
        self.notes = notes
        self.patients = patients
        self.matching = matching
        self.max_runs = max_runs
        self._runs: OrderedDict[str, Run] = OrderedDict()
        self._lock = threading.Lock()
        # One run at a time: the GPU models and the LLM quotas are shared.
        self._executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="mmai-run"
        )

    # ---- job API ----------------------------------------------------------
    def start(self, mrn: str, options: dict[str, Any] | None = None) -> Run:
        run = Run(
            id=uuid.uuid4().hex[:12],
            mrn=str(mrn).strip(),
            options=RunOptions.from_dict(options),
        )
        with self._lock:
            self._runs[run.id] = run
            while len(self._runs) > self.max_runs:
                self._runs.popitem(last=False)
        self._executor.submit(self._execute, run)
        return run

    def get(self, run_id: str) -> Run | None:
        return self._runs.get(run_id)

    def list(self) -> list[Run]:
        return list(reversed(self._runs.values()))

    def run_sync(self, mrn: str, options: dict[str, Any] | None = None) -> Run:
        run = Run(
            id=uuid.uuid4().hex[:12],
            mrn=str(mrn).strip(),
            options=RunOptions.from_dict(options),
        )
        with self._lock:
            self._runs[run.id] = run
        self._executor.submit(self._execute, run).result()
        return run

    # ---- execution --------------------------------------------------------
    def _timed(self, run: Run, key: str, fn: Callable[[], Any], *, skip: bool = False):
        step = run.step(key)
        if skip:
            step["status"] = "skipped"
            return None
        step["status"] = "running"
        started = time.time()
        try:
            value = fn()
        except Exception:
            step["status"] = "error"
            step["seconds"] = round(time.time() - started, 2)
            raise
        step["status"] = "done"
        step["seconds"] = round(time.time() - started, 2)
        return value

    def _execute(self, run: Run) -> None:
        run.status = "running"
        try:
            self._pipeline(run)
            run.status = "done"
        except Exception as exc:  # noqa: BLE001
            run.status = "error"
            # Type + message only; the traceback could include note text.
            run.error = f"{type(exc).__name__}: {exc}"[:500]
            logger.error("Run %s failed: %s", run.id, type(exc).__name__)
            logger.debug("".join(traceback.format_exception_only(exc)))

    def _pipeline(self, run: Run) -> None:
        opts = run.options
        result = run.result
        result["models"] = {
            "summary_llm": self.patients.summary_model,
            "embedding": self.matching.config.embedding.get("model_path"),
            "match_quality": self.matching.config.raw["match_quality"]["model_name"],
            "exclusion": self.matching.config.raw["exclusion_criteria"]["model_name"],
            "review_llm": self.matching.config.llm_match_quality["remote"][
                "model_name"
            ],
        }

        notes = self._timed(run, "notes", lambda: self.notes.get_notes(run.mrn))
        run.step("notes")["detail"] = f"{len(notes)} notes"
        result["notes"] = records(notes)

        # Summary and journey only depend on the notes: run them concurrently.
        with ThreadPoolExecutor(max_workers=2) as pool:
            journey_future = pool.submit(
                self._timed,
                run,
                "journey",
                lambda: self.patients.journey(notes),
                skip=not opts.include_journey,
            )
            summary = self._timed(
                run, "summary", lambda: self.patients.summarize(notes)
            )
            result["summary"] = summary
            try:
                result["journey"] = journey_future.result() or {
                    "headline": "",
                    "events": [],
                }
            except Exception as exc:  # noqa: BLE001 - the journey is optional
                run.step("journey")["detail"] = type(exc).__name__
                result["journey"] = {"headline": "", "events": []}
        if not summary["ok"]:
            raise RuntimeError("Patient summary was empty or non-informative")
        patient_id = summary["patient_id"]

        candidates = self._timed(
            run,
            "retrieve",
            lambda: self.matching.candidates(
                patient_id, summary["cancer_history_summary"], k=opts.top_k
            ),
        )
        run.step("retrieve")["detail"] = (
            f"{len(candidates)} spaces / {candidates['trial_id'].nunique()} trials"
        )

        pairs = candidates.assign(
            cancer_history_summary=summary["cancer_history_summary"],
            general_exclusion_criteria_evidence=summary[
                "general_exclusion_criteria_evidence"
            ],
        )
        quality = self._timed(run, "quality", lambda: self.matching.score(pairs))
        scored = pairs.merge(quality, on=["patient_id", "space_trial_id"])
        result["candidates"] = records(
            scored.drop(
                columns=[
                    "cancer_history_summary",
                    "general_exclusion_criteria_evidence",
                ]
            ).sort_values("match_quality_score", ascending=False)
        )

        trial_pairs = scored.drop_duplicates("trial_id")
        exclusion = self._timed(
            run, "exclusion", lambda: self.matching.exclusion(trial_pairs)
        )

        # Best-scoring space per trial is the trial's representative match.
        best = (
            scored.sort_values("match_quality_score", ascending=False)
            .drop_duplicates("trial_id")
            .merge(exclusion, on=["patient_id", "trial_id"], how="left")
            .reset_index(drop=True)
        )

        def review():
            top = best[best["match_quality_pass"]].head(opts.llm_review_top_n)
            if top.empty:
                return None
            return self.matching.llm_review(top)

        reviewed = self._timed(run, "review", review, skip=not opts.llm_review)
        if reviewed is not None:
            best = best.merge(
                reviewed.drop(columns=["space_trial_id"]),
                on=["patient_id", "trial_id"],
                how="left",
            )

        def finalize():
            cutoff = self.matching.score_cutoff
            decisions = best.apply(lambda r: decide(r, cutoff), axis=1)
            best["decision"] = [d for d, _ in decisions]
            best["decision_reasons"] = [r for _, r in decisions]
            order = {ELIGIBLE: 0, REVIEW: 1, NOT_MATCHED: 2}
            ranked = best.sort_values(
                ["decision", "match_quality_score"],
                key=lambda col: col.map(order) if col.name == "decision" else -col,
            ).reset_index(drop=True)
            ranked["rank"] = range(1, len(ranked) + 1)
            return ranked

        decided = self._timed(run, "decide", finalize)
        counts = decided["decision"].value_counts().to_dict()
        run.step("decide")["detail"] = ", ".join(f"{v} {k}" for k, v in counts.items())
        result["decisions"] = records(
            decided.drop(
                columns=[
                    "cancer_history_summary",
                    "general_exclusion_criteria_evidence",
                ]
            )
        )
        result["score_cutoff"] = self.matching.score_cutoff
