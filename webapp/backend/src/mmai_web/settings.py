"""Runtime settings, read from the environment (and ``webapp/backend/.env``)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parents[1]
EXAMPLES_DIR = REPO_ROOT / "examples"


def _paths(value: str | None, default: list[Path]) -> list[Path]:
    if not value:
        return default
    return [Path(p).expanduser() for p in value.split(os.pathsep) if p.strip()]


@dataclass(frozen=True)
class Settings:
    mmai_config_path: Path
    notes_sources: list[Path]
    trial_summaries_path: Path
    trials_path: Path
    cache_dir: Path
    summary_model: str
    apigee_base_url: str
    apigee_client_id: str | None
    apigee_client_secret: str | None
    openai_timeout_s: float
    host: str
    port: int
    cors_origins: list[str] = field(default_factory=list)

    @classmethod
    def from_env(cls) -> Settings:
        load_dotenv(BACKEND_DIR / ".env")
        env = os.environ.get
        return cls(
            mmai_config_path=Path(
                env("MMAI_WEB_CONFIG", str(BACKEND_DIR / "config" / "mmai_web.yaml"))
            ),
            # Synthetic example notes by default. Point this at real data (for
            # example H:\data\mm-ai\mayo_dataset_10.csv) through the env var.
            notes_sources=_paths(
                env("MMAI_WEB_NOTES_SOURCES"),
                [
                    EXAMPLES_DIR / "data" / "note_set_1.csv",
                    EXAMPLES_DIR / "data" / "note_set_2.csv",
                ],
            ),
            # The 31B reference trial spaces for the 10 example trials.
            trial_summaries_path=Path(
                env(
                    "MMAI_WEB_TRIAL_SUMMARIES",
                    str(EXAMPLES_DIR / "output" / "trial_summaries.csv"),
                )
            ),
            trials_path=Path(
                env(
                    "MMAI_WEB_TRIALS",
                    str(EXAMPLES_DIR / "data" / "trials_for_summarize.csv"),
                )
            ),
            # Trial embeddings and model metadata only; never patient data.
            cache_dir=Path(env("MMAI_WEB_CACHE_DIR", str(BACKEND_DIR / ".cache"))),
            summary_model=env("MMAI_WEB_SUMMARY_MODEL", "gpt-5.6-luna"),
            apigee_base_url=env("APIGEE_BASE_URL", "https://mcc.apix.mayo.edu"),
            apigee_client_id=env("APIGEEX_CLIENT_ID"),
            apigee_client_secret=env("APIGEEX_CLIENT_SECRET"),
            openai_timeout_s=float(env("MMAI_WEB_OPENAI_TIMEOUT", "600")),
            host=env("MMAI_WEB_HOST", "127.0.0.1"),
            port=int(env("MMAI_WEB_PORT", "5050")),
            cors_origins=[
                o.strip()
                for o in env("MMAI_WEB_CORS_ORIGINS", "http://localhost:5173").split(
                    ","
                )
                if o.strip()
            ],
        )
