"""JSON-safe conversion of DataFrames."""

from __future__ import annotations

import json
from typing import Any

import pandas as pd


def records(df: pd.DataFrame) -> list[dict[str, Any]]:
    """DataFrame -> list of plain dicts (NaN -> None, numpy -> Python, ISO dates)."""
    serializable = df.drop(columns=["embedding"], errors="ignore")
    return json.loads(serializable.to_json(orient="records", date_format="iso"))
