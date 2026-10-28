"""LLM backend routing for the matchminer-ai package, without modifying it.

The package resolves its LLM backend through ``get_llm_backend(config)``, which
``patients.summarize``, ``trials.summarize`` and ``matching.llm_checks`` import
by name. ``install()``
replaces those module attributes with a router that sends any task whose config
section has ``provider: openai_responses`` to the Apigee Responses API and every
other task to the package's own backend (llama.cpp / vLLM).

It also swaps the patient prompt-building process pool for a thread pool: a
spawned multiprocessing pool inside a web server re-imports the server entry
point on Windows, and the prompt builder is cheap enough to run in-process.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from multiprocessing.pool import ThreadPool
from typing import Any

from matchminer_ai.llm import backends as mmai_backends
from matchminer_ai.llm.backends import LLMGenerationResult
from matchminer_ai.llm.prompt_rendering import Prompt

from .apigee import ApigeeOpenAI

logger = logging.getLogger(__name__)

PROVIDER_KEY = "provider"
OPENAI_RESPONSES = "openai_responses"


@dataclass
class OpenAIResponsesBackend:
    """Package-compatible backend that calls the OpenAI Responses API."""

    openai: ApigeeOpenAI

    def _one(self, prompt: Prompt, llm_config: dict[str, Any]) -> tuple[str, str, str]:
        task_remote = dict(llm_config.get("remote", {}))
        try:
            response = self.openai.respond(
                model=str(llm_config["model_name"]),
                messages=list(prompt.messages or []),
                max_output_tokens=int(prompt.max_tokens),
                reasoning_effort=task_remote.get("reasoning_effort"),
            )
        except Exception as exc:  # noqa: BLE001 - surfaced as finish_reason
            # Exception text can echo request content; log the type only.
            logger.warning(
                "Responses request %d failed: %s", prompt.row_idx, type(exc).__name__
            )
            return "", "", "error"
        if response.status == "incomplete":
            finish_reason = "length"
        elif response.status == "completed":
            finish_reason = "stop"
        else:
            finish_reason = "error"
        reasoning = "\n".join(
            part.text
            for item in response.output
            if item.type == "reasoning"
            for part in (getattr(item, "summary", None) or [])
        )
        return response.output_text or "", reasoning, finish_reason

    def generate_llm_outputs(
        self,
        *,
        prompt_list: list[Prompt],
        llm_config: dict[str, Any],
        model_metadata_cache_dir: str | None = None,
    ) -> LLMGenerationResult:
        workers = int(dict(llm_config.get("remote", {})).get("max_concurrency", 4))
        ordered = sorted(prompt_list, key=lambda p: p.row_idx)
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            results = list(pool.map(lambda p: self._one(p, llm_config), ordered))
        return LLMGenerationResult(
            final_outputs=[text for text, _r, _f in results],
            model_metadata={},
            finish_reasons=[finish for _t, _r, finish in results],
            reasoning_outputs=[reasoning for _t, reasoning, _f in results],
            raw_outputs=[],
        )


@dataclass
class RoutingBackend:
    """Pick a backend per call from the task's ``provider`` key."""

    default: Any
    responses: OpenAIResponsesBackend

    def generate_llm_outputs(self, *, llm_config: dict[str, Any], **kwargs: Any):
        backend = (
            self.responses
            if llm_config.get(PROVIDER_KEY) == OPENAI_RESPONSES
            else self.default
        )
        return backend.generate_llm_outputs(llm_config=llm_config, **kwargs)

    def truncate_texts(self, *args: Any, **kwargs: Any):
        return self.default.truncate_texts(*args, **kwargs)


_installed = False


def install(openai: ApigeeOpenAI) -> None:
    """Patch the package's backend lookups (idempotent)."""
    global _installed
    if _installed:
        return

    from matchminer_ai.matching import llm_checks
    from matchminer_ai.patients import prompt_builder
    from matchminer_ai.patients import summarize as patient_summarize
    from matchminer_ai.trials import summarize as trial_summarize

    responses_backend = OpenAIResponsesBackend(openai)
    original_get_backend = mmai_backends.get_llm_backend

    def get_llm_backend(config):
        return RoutingBackend(original_get_backend(config), responses_backend)

    def prep_prompt_pool(patient_config, n_workers=1):
        return ThreadPool(
            processes=max(1, int(n_workers)),
            initializer=prompt_builder._init_prompt_worker,
            initargs=(patient_config,),
        )

    patient_summarize.get_llm_backend = get_llm_backend
    trial_summarize.get_llm_backend = get_llm_backend
    llm_checks.get_llm_backend = get_llm_backend
    patient_summarize.prep_prompt_pool = prep_prompt_pool
    _installed = True
