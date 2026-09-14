"""
agents/coordinator/validation_log.py
--------------------------------------
Appends one row per Validation-node decision to eval_logs/validation_log.csv,
for the "Self-Correction Pass-Rate Stats" preliminary evaluation (see
docagent_evaluation_plan.md, Section 1).

Called from Coordinator._validation_router() right before each route
decision is returned. Not used in the request-serving path for anything
functional — purely an evaluation-time side channel, so failures here must
never break the pipeline.
"""

from __future__ import annotations

import csv
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

EVAL_LOG_PATH = Path(__file__).resolve().parents[2] / "eval_logs" / "validation_log.csv"

_CSV_HEADER = ["timestamp", "doc_id", "cycle", "score", "routed_to", "per_document_scores"]


def log_validation_event(
    doc_id: str,
    cycle: int,
    score: float,
    routed_to: str,
    per_document_scores: dict[str, float] | None = None,
) -> None:
    """Append one validation-decision row to the eval CSV log.

    Args:
        doc_id:               Stable identifier for the run being validated,
                               e.g. "{commit_sha}:{workflow_id}".
        cycle:                Revision cycle number at the time of this
                               validation (0 = first pass).
        score:                Aggregate quality_score (0-100) at this cycle.
        routed_to:             One of "sync" | "revision" | "failed".
        per_document_scores:  Optional per-document score breakdown, stored
                               as a JSON string for later fine-grained analysis.
    """
    try:
        EVAL_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        is_new_file = not EVAL_LOG_PATH.exists()

        with open(EVAL_LOG_PATH, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if is_new_file:
                writer.writerow(_CSV_HEADER)
            writer.writerow([
                datetime.now(timezone.utc).isoformat(),
                doc_id,
                cycle,
                round(score, 2),
                routed_to,
                json.dumps(per_document_scores or {}),
            ])
    except OSError as exc:
        logger.warning("validation_log: could not write to %s: %s", EVAL_LOG_PATH, exc)
