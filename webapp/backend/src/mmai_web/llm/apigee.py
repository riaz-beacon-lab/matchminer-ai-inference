"""Mayo Apigee OAuth + OpenAI Responses API client.

Mirrors apigee-workbench/openai-demo/main.py: a client-credentials OAuth token
is exchanged at ``/oauth/token`` and passed to the OpenAI SDK as ``api_key``.
Tokens live ~1 hour, so the client is cached and rebuilt shortly before expiry.
"""

from __future__ import annotations

import threading
import time
from typing import Any

import requests
from openai import OpenAI

from mmai_web.settings import Settings


class ApigeeOpenAI:
    """Thread-safe provider of an authenticated OpenAI client."""

    # Refresh this many seconds before the token's stated expiry.
    _REFRESH_MARGIN_S = 300

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._lock = threading.Lock()
        self._client: OpenAI | None = None
        self._expires_at = 0.0

    @property
    def configured(self) -> bool:
        return bool(
            self._settings.apigee_client_id and self._settings.apigee_client_secret
        )

    def _fetch_token(self) -> tuple[str, float]:
        if not self.configured:
            raise RuntimeError(
                "APIGEEX_CLIENT_ID / APIGEEX_CLIENT_SECRET are not set; see "
                "webapp/backend/dotenv.tpl."
            )
        response = requests.post(
            f"{self._settings.apigee_base_url}/oauth/token",
            data={
                "grant_type": "client_credentials",
                "client_id": self._settings.apigee_client_id,
                "client_secret": self._settings.apigee_client_secret,
            },
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        token = payload.get("access_token")
        if not token:
            raise RuntimeError("Apigee OAuth response did not contain access_token")
        return token, time.time() + float(payload.get("expires_in", 3600))

    def client(self) -> OpenAI:
        with self._lock:
            if self._client is None or time.time() >= (
                self._expires_at - self._REFRESH_MARGIN_S
            ):
                token, self._expires_at = self._fetch_token()
                self._client = OpenAI(
                    api_key=token,
                    base_url=(
                        f"{self._settings.apigee_base_url}"
                        "/llm-azure-openai-v1/openai/v1"
                    ),
                    timeout=self._settings.openai_timeout_s,
                    max_retries=3,
                )
            return self._client

    def respond(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        max_output_tokens: int,
        reasoning_effort: str | None = None,
        json_schema: dict[str, Any] | None = None,
    ) -> Any:
        """Call ``responses.create`` and return the raw response object."""
        kwargs: dict[str, Any] = {
            "model": model,
            # Empty system messages (the package emits one for non gpt-oss
            # models) are rejected by some deployments, so drop them.
            "input": [m for m in messages if str(m.get("content", "")).strip()],
            "max_output_tokens": max_output_tokens,
        }
        if reasoning_effort:
            kwargs["reasoning"] = {"effort": reasoning_effort}
        if json_schema is not None:
            kwargs["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": json_schema.get("title", "result"),
                    "strict": True,
                    "schema": json_schema,
                }
            }
        return self.client().responses.create(**kwargs)
