"""Runtime telemetry for the frontend debugging workspace."""

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query

from app.core.config import settings

router = APIRouter()


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _workflow_snapshots() -> list[dict[str, Any]]:
    workflow_root = settings.workflow_path_dir
    if not workflow_root.exists():
        return []
    workflows = [_read_json(path, {}) for path in workflow_root.glob("*.json")]
    return sorted(
        (workflow for workflow in workflows if workflow),
        key=lambda workflow: workflow.get("timestamp", ""),
        reverse=True,
    )


def _active_chunk_counts() -> dict[str, int]:
    storage_root = Path("rag/storage/storage")
    faiss = _read_json(storage_root / "faiss" / "metadata.json", {})
    bm25 = _read_json(storage_root / "bm25" / "bm25_metadata.json", {})

    faiss_chunks = faiss.get("chunks", {}).values()
    bm25_chunks = bm25.get("chunks", [])
    return {
        "vector": sum(chunk.get("metadata", {}).get("active", False) for chunk in faiss_chunks),
        "keyword": sum(chunk.get("metadata", {}).get("active", False) for chunk in bm25_chunks),
    }


def _workflow_logs(workflow_id: str, limit: int = 80) -> list[str]:
    path = Path("logs") / f"{workflow_id}.log"
    if not path.exists():
        return []
    try:
        return [line.rstrip() for line in path.read_text(encoding="utf-8").splitlines()[-limit:]]
    except OSError:
        return []


@router.get("/snapshot")
async def debug_snapshot(
    workflow_id: str | None = Query(default=None),
) -> dict[str, Any]:
    """Return the newest workflow's RAG state and recent filtered pipeline logs."""
    workflows = _workflow_snapshots()
    workflow = next(
        (item for item in workflows if item.get("workflow_id") == workflow_id),
        workflows[0] if workflows else {},
    )
    selected_id = workflow.get("workflow_id", "")

    return {
        "backend": {"status": "healthy"},
        "indexes": _active_chunk_counts(),
        "workflow": workflow,
        "logs": _workflow_logs(selected_id),
        "recent_workflows": [
            {
                "workflow_id": item.get("workflow_id"),
                "repository": item.get("repository"),
                "status": item.get("status"),
                "timestamp": item.get("timestamp"),
            }
            for item in workflows[:10]
        ],
    }
