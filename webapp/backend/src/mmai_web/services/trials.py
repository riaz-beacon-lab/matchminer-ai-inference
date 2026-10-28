"""Trial service: trial corpus, clinical spaces, and their embeddings."""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from pathlib import Path
from typing import Any

import pandas as pd
from matchminer_ai.config import MMAIConfig
from matchminer_ai.embedding import embed_for_matching
from matchminer_ai.trials import summarize_trials

from mmai_web.services.serialize import records

logger = logging.getLogger(__name__)

TRIAL_INFO_COLUMNS = [
    "trial_id",
    "trial_title",
    "brief_summary",
    "eligibility_criteria",
]


class TrialNotFound(LookupError):
    pass


class TrialService:
    """Holds the matching corpus: trial spaces + cached space embeddings."""

    def __init__(
        self,
        config: MMAIConfig,
        *,
        trial_summaries_path: Path,
        trials_path: Path,
        cache_dir: Path,
        gpu_lock: threading.Lock,
    ) -> None:
        self.config = config
        self.cache_dir = cache_dir
        self.gpu_lock = gpu_lock
        self._lock = threading.Lock()
        self.spaces = pd.read_csv(trial_summaries_path)
        trials = pd.read_csv(trials_path)
        self.trial_info = trials[
            [c for c in TRIAL_INFO_COLUMNS if c in trials.columns]
        ].drop_duplicates("trial_id")
        self._embedded: pd.DataFrame | None = None

    # ---- corpus -----------------------------------------------------------
    def list_trials(self) -> list[dict[str, Any]]:
        counts = self.spaces.groupby("trial_id").size().rename("n_spaces")
        table = (
            counts.reset_index()
            .merge(
                self.trial_info[["trial_id", "trial_title"]], on="trial_id", how="left"
            )
            .sort_values("trial_id")
        )
        return records(table)

    def get_trial(self, trial_id: str) -> dict[str, Any]:
        spaces = self.spaces[self.spaces["trial_id"] == trial_id]
        if spaces.empty:
            raise TrialNotFound(trial_id)
        info = self.trial_info[self.trial_info["trial_id"] == trial_id]
        return {
            "trial_id": trial_id,
            **(records(info)[0] if not info.empty else {}),
            "spaces": records(spaces.sort_values("clinical_space_number")),
        }

    def space_table(self) -> pd.DataFrame:
        return self.spaces.merge(
            self.trial_info[["trial_id", "trial_title"]], on="trial_id", how="left"
        )

    # ---- embeddings -------------------------------------------------------
    def _cache_path(self) -> Path:
        digest = hashlib.sha256(
            json.dumps(
                [
                    self.config.embedding.get("model_path"),
                    self.spaces[["space_trial_id", "clinical_space_summary"]]
                    .astype(str)
                    .values.tolist(),
                ]
            ).encode()
        ).hexdigest()[:16]
        return self.cache_dir / f"embedded_trial_spaces_{digest}.parquet"

    def embedded_spaces(self) -> pd.DataFrame:
        with self._lock:
            if self._embedded is None:
                path = self._cache_path()
                if path.exists():
                    self._embedded = pd.read_parquet(path)
                else:
                    logger.info("Embedding %d trial spaces.", len(self.spaces))
                    with self.gpu_lock:
                        embedded = embed_for_matching(
                            self.spaces, entity_type="trial", config=self.config
                        )
                    path.parent.mkdir(parents=True, exist_ok=True)
                    embedded.to_parquet(path)
                    self._embedded = embedded
            return self._embedded

    # ---- summarization ----------------------------------------------------
    def summarize(
        self, trials: pd.DataFrame, *, add_to_corpus: bool = False
    ) -> dict[str, Any]:
        """Extract clinical spaces for new trials with the summary LLM."""
        spaces, qc = summarize_trials(trials, config=self.config, return_qc=True)
        if add_to_corpus and not spaces.empty:
            with self._lock:
                keep = ~self.spaces["trial_id"].isin(spaces["trial_id"])
                self.spaces = pd.concat(
                    [self.spaces[keep], spaces[self.spaces.columns]], ignore_index=True
                )
                info = trials[[c for c in TRIAL_INFO_COLUMNS if c in trials.columns]]
                self.trial_info = pd.concat(
                    [
                        self.trial_info[
                            ~self.trial_info["trial_id"].isin(info["trial_id"])
                        ],
                        info,
                    ],
                    ignore_index=True,
                )
                self._embedded = None
        return {"spaces": records(spaces), "qc": records(qc)}
