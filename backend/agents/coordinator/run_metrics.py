"""
agents/coordinator/run_metrics.py
------------------------------------
Computes a snapshot of run-level KPIs for the analytics dashboard, entirely
from data already present in SharedMemory at the end of a workflow run.

No RAG queries, no filesystem reads beyond the one JSON write, no LLM calls
except the faithfulness score (see ValidationAgent._compute_faithfulness_score,
which runs *during* validation and is already priced into the measured
generation time — nothing here adds extra latency on top of that).

Called by Coordinator.start_workflow() after the graph completes, using the
final AgentWorkflowState's execution_time (the pipeline's real end-to-end
duration — SharedMemory.workflow.execution_times only has the sync step's
own duration, not the full run).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agents.memory.shared_memory import SharedMemory

logger = logging.getLogger(__name__)


def compute_run_metrics(shared_memory: SharedMemory, total_execution_time: float) -> dict[str, Any]:
    """Build the metrics snapshot dict for one completed workflow run.

    Args:
        shared_memory:         Final SharedMemory state after the graph completes.
        total_execution_time:  Real end-to-end duration in seconds
                                (AgentWorkflowState.execution_time).

    Returns:
        dict: JSON-serialisable metrics snapshot.
    """
    validation = shared_memory.validation
    stats = shared_memory.metadata.statistics

    documents_generated = len(
        [v for v in shared_memory.documentation.file_docs.values() if v and v.strip()]
    )
    avg_time_per_doc = (
        round(total_execution_time / documents_generated, 2) if documents_generated else 0.0
    )

    test_files = stats.test_files
    source_files = stats.source_files
    test_coverage_ratio = round(test_files / source_files, 4) if source_files else 0.0

    return {
        "workflow_id": shared_memory.workflow.workflow_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "quality_score": round(validation.quality_score, 1),
        "faithfulness_score": round(validation.faithfulness_score, 1),
        "faithfulness_notes": validation.faithfulness_notes,
        "generation_time_seconds": round(total_execution_time, 2),
        "documents_generated": documents_generated,
        "average_time_per_document_seconds": avg_time_per_doc,
        "test_files": test_files,
        "source_files": source_files,
        "test_coverage_ratio": test_coverage_ratio,
    }


def write_run_metrics(shared_memory: SharedMemory, total_execution_time: float) -> None:
    """Compute and persist the run-metrics snapshot to metrics.json.

    Writes into the same per-repo output directory SyncAgent just wrote docs
    to (shared_memory.workflow.output_directory). No-ops with a warning if
    that path wasn't set (e.g. sync failed before this point).
    """
    output_directory = shared_memory.workflow.output_directory
    if not output_directory:
        logger.warning("run_metrics: no output_directory in shared_memory — skipping metrics.json")
        return

    metrics = compute_run_metrics(shared_memory, total_execution_time)
    path = Path(output_directory) / "metrics.json"
    try:
        path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
        logger.info("Run metrics written: %s", path)
    except OSError as exc:
        logger.warning("Could not write run metrics to %s: %s", path, exc)
