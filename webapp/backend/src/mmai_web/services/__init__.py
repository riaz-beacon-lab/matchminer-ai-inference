"""Service layer shared by the Flask API and the MCP server.

``get_services()`` builds every service once per process. Each service is
usable on its own from other Python apps as well.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from functools import lru_cache

from matchminer_ai import load_config
from matchminer_ai.config import MMAIConfig

from mmai_web.llm import backends
from mmai_web.llm.apigee import ApigeeOpenAI
from mmai_web.services.matching import EmbeddingService, MatchingService
from mmai_web.services.notes import CsvNotesProvider, NotesService
from mmai_web.services.patients import PatientService
from mmai_web.services.pipeline import PipelineService
from mmai_web.services.trials import TrialService
from mmai_web.settings import Settings


@dataclass
class Services:
    settings: Settings
    config: MMAIConfig
    openai: ApigeeOpenAI
    notes: NotesService
    patients: PatientService
    trials: TrialService
    embedding: EmbeddingService
    matching: MatchingService
    pipeline: PipelineService


def load_mmai_config(settings: Settings) -> MMAIConfig:
    config = load_config(settings.mmai_config_path)
    # Keep the package's metadata cache next to the web app, not in the CWD.
    config.model_metadata_cache_dir = str(settings.cache_dir / "model_metadata")
    for section in (config.patient, config.trial):
        if section.get("provider") == backends.OPENAI_RESPONSES:
            section["remote"]["model_name"] = settings.summary_model
    return config


@lru_cache(maxsize=1)
def get_services() -> Services:
    settings = Settings.from_env()
    config = load_mmai_config(settings)
    openai = ApigeeOpenAI(settings)
    backends.install(openai)

    gpu_lock = threading.Lock()
    notes = NotesService(CsvNotesProvider(settings.notes_sources))
    patients = PatientService(config, openai)
    trials = TrialService(
        config,
        trial_summaries_path=settings.trial_summaries_path,
        trials_path=settings.trials_path,
        cache_dir=settings.cache_dir,
        gpu_lock=gpu_lock,
    )
    embedding = EmbeddingService(config, gpu_lock)
    matching = MatchingService(config, trials, gpu_lock)
    pipeline = PipelineService(notes, patients, matching)
    return Services(
        settings=settings,
        config=config,
        openai=openai,
        notes=notes,
        patients=patients,
        trials=trials,
        embedding=embedding,
        matching=matching,
        pipeline=pipeline,
    )
