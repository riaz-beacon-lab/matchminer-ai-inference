"""Embedding + matching services over the trial corpus."""

from __future__ import annotations

import threading
from dataclasses import replace
from typing import Any

import pandas as pd
from matchminer_ai.config import MMAIConfig
from matchminer_ai.embedding import embed_for_matching, embed_texts
from matchminer_ai.matching import (
    exclusion_criteria_check,
    exclusion_criteria_check_with_llm,
    generate_candidate_matches,
    score_match_quality,
    score_match_quality_with_llm,
)

from mmai_web.services.trials import TrialService


class EmbeddingService:
    def __init__(self, config: MMAIConfig, gpu_lock: threading.Lock) -> None:
        self.config = config
        self.gpu_lock = gpu_lock

    def embed(self, texts: list[str]) -> dict[str, Any]:
        with self.gpu_lock:
            vectors, metadata = embed_texts(texts, config=self.config)
        return {"embeddings": [list(map(float, v)) for v in vectors], "model": metadata}


class MatchingService:
    def __init__(
        self, config: MMAIConfig, trials: TrialService, gpu_lock: threading.Lock
    ) -> None:
        self.config = config
        self.trials = trials
        self.gpu_lock = gpu_lock

    @property
    def score_cutoff(self) -> float:
        return float(self.config.raw.get("match_quality", {}).get("score_cutoff", 0.2))

    def candidates(
        self, patient_id: str, cancer_history_summary: str, *, k: int = 20
    ) -> pd.DataFrame:
        """Top-k trial spaces by TrialSpace cosine similarity."""
        patient = pd.DataFrame(
            [
                {
                    "patient_id": patient_id,
                    "cancer_history_summary": cancer_history_summary,
                }
            ]
        )
        corpus = self.trials.embedded_spaces()
        with self.gpu_lock:
            embedded = embed_for_matching(
                patient, entity_type="patient", config=self.config
            )
        found = generate_candidate_matches(query_df=embedded, corpus_df=corpus, k=k)
        return found.merge(self.trials.space_table(), on="space_trial_id", how="left")

    def score(self, pairs: pd.DataFrame) -> pd.DataFrame:
        """TrialChecker match quality for each (patient summary, space) pair."""
        with self.gpu_lock:
            return score_match_quality(
                pairs, config=self.config, filter_low_quality=False
            )

    def exclusion(self, pairs: pd.DataFrame) -> pd.DataFrame:
        """BoilerplateChecker: does the patient pass the trial's general exclusions?"""
        with self.gpu_lock:
            return exclusion_criteria_check(pairs, config=self.config)

    def llm_review(self, pairs: pd.DataFrame) -> pd.DataFrame:
        """Local-LLM (llama.cpp) match-quality score + exclusion verdict, with text.

        ``pairs`` needs patient_id, space_trial_id, trial_id and the four
        summary / criteria text columns.
        """
        # debug_mode keeps the answer text, which is the reviewer's rationale.
        config = replace(self.config, debug_mode=True)
        quality = score_match_quality_with_llm(pairs, config=config)
        exclusion = exclusion_criteria_check_with_llm(
            pairs.drop_duplicates(["patient_id", "trial_id"]), config=config
        )
        return quality.merge(
            pairs[["patient_id", "space_trial_id", "trial_id"]],
            on=["patient_id", "space_trial_id"],
        ).merge(exclusion, on=["patient_id", "trial_id"], how="left")
