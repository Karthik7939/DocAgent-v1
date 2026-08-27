"""
rag/indexing/index_stats.py
------------------------------
Persists the indexing timing breakdown that BootstrapIndexer and
IncrementalIndexer already compute and log, so it's queryable by the API
instead of only visible in log output.

One JSON file per repository at storage_root/index_stats/<slug>.json, holding
the most recent bootstrap run and the most recent incremental run separately
— together they tell the "full rebuild vs. incremental update" story.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Optional

from rag.config import settings
from rag.utils import get_logger

logger = get_logger(__name__)


def _stats_path(repository_name: str) -> Path:
    slug = repository_name.replace("/", "_")
    return settings.storage_root / "index_stats" / f"{slug}.json"


def write_index_stats(repository_name: str, run_type: str, stats: dict[str, Any]) -> None:
    """Persist one indexing run's timing breakdown.

    Args:
        repository_name: Full repository name, e.g. 'owner/repo'.
        run_type:         'bootstrap' or 'incremental'.
        stats:            Timing/count fields for this run (chunk_count,
                           chunk_time_seconds, embed_time_seconds, etc.).
    """
    path = _stats_path(repository_name)
    existing: dict[str, Any] = {}
    if path.is_file():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            existing = {}

    existing[run_type] = {**stats, "recorded_at": time.time()}

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    except OSError as exc:
        logger.warning("Could not write index stats for %s: %s", repository_name, exc)


def read_index_stats(repository_name: str) -> Optional[dict[str, Any]]:
    """Return the persisted indexing stats for a repository, or None."""
    path = _stats_path(repository_name)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
