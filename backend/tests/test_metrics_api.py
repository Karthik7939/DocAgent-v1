"""
tests/test_metrics_api.py
----------------------------
Unit tests for GET /api/metrics/{repo_slug}

Tests:
- 404 for an unknown repository
- 400 for a path-traversal / slash-containing slug
- Returns run_metrics when metrics.json exists
- has_run_metrics is False and run_metrics is None when metrics.json is absent
- Commits/contributors parsed correctly from CHANGELOG.md (both formats)
- Malformed metrics.json degrades gracefully instead of 500ing
"""

import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import settings

client = TestClient(app)


@pytest.fixture()
def docs_root(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "generated_docs_path", str(tmp_path))
    return tmp_path


def test_unknown_repository_404(docs_root):
    res = client.get("/api/metrics/Owner_does-not-exist")
    assert res.status_code == 404


def test_slash_in_slug_rejected(docs_root):
    res = client.get("/api/metrics/Owner%2Frepo")
    assert res.status_code in (400, 404)  # FastAPI may 404 on the unmatched route too


def test_no_metrics_json_yet(docs_root):
    repo_dir = docs_root / "Owner_repo"
    repo_dir.mkdir()

    res = client.get("/api/metrics/Owner_repo")
    assert res.status_code == 200
    body = res.json()
    assert body["repository"] == "Owner/repo"
    assert body["has_run_metrics"] is False
    assert body["run_metrics"] is None
    assert body["commits_documented"] == 0
    assert body["contributors_tracked"] == 0


def test_returns_run_metrics_when_present(docs_root):
    repo_dir = docs_root / "Owner_repo"
    repo_dir.mkdir()
    (repo_dir / "metrics.json").write_text(
        json.dumps({
            "workflow_id": "wf-1",
            "generated_at": "2026-08-27T00:00:00+00:00",
            "quality_score": 91.2,
            "faithfulness_score": 88.5,
            "faithfulness_notes": "None",
            "generation_time_seconds": 42.1,
            "documents_generated": 6,
            "average_time_per_document_seconds": 7.0,
            "test_files": 10,
            "source_files": 40,
            "test_coverage_ratio": 0.25,
        }),
        encoding="utf-8",
    )

    res = client.get("/api/metrics/Owner_repo")
    assert res.status_code == 200
    body = res.json()
    assert body["has_run_metrics"] is True
    assert body["run_metrics"]["quality_score"] == 91.2
    assert body["run_metrics"]["faithfulness_score"] == 88.5


def test_malformed_metrics_json_degrades_gracefully(docs_root):
    repo_dir = docs_root / "Owner_repo"
    repo_dir.mkdir()
    (repo_dir / "metrics.json").write_text("{not valid json", encoding="utf-8")

    res = client.get("/api/metrics/Owner_repo")
    assert res.status_code == 200
    body = res.json()
    assert body["has_run_metrics"] is False
    assert body["run_metrics"] is None


def test_changelog_parsing_new_format(docs_root):
    repo_dir = docs_root / "Owner_repo"
    repo_dir.mkdir()
    (repo_dir / "CHANGELOG.md").write_text(
        "# Changelog\n\n"
        "## [abc12345] Fixed a bug\n"
        "**Date:** 2026-08-27  **Time:** 10:00:00\n"
        "**Author:** Alice\n"
        "**Branch:** `main`\n"
        "**Commit Message:** Fixed a bug\n\n---\n\n"
        "## [def67890] Added a feature\n"
        "**Date:** 2026-08-26  **Time:** 09:00:00\n"
        "**Author:** Bob\n"
        "**Branch:** `main`\n"
        "**Commit Message:** Added a feature\n\n---\n",
        encoding="utf-8",
    )

    res = client.get("/api/metrics/Owner_repo")
    body = res.json()
    assert body["commits_documented"] == 2
    assert body["contributors_tracked"] == 2
    assert set(body["contributors"]) == {"Alice", "Bob"}


def test_changelog_parsing_old_format_and_repeat_author(docs_root):
    """Old format (pre Date/Time fix) plus a repeated author should still work."""
    repo_dir = docs_root / "Owner_repo"
    repo_dir.mkdir()
    (repo_dir / "CHANGELOG.md").write_text(
        "# Changelog\n\n"
        "## [eb037a7b] — 2026-08-25T11:34:30+05:30\n"
        "**Author:** Alice  \n"
        "**Branch:** `main`\n\n---\n\n"
        "## [7b0f819e] — 2026-08-24T21:55:04+05:30\n"
        "**Author:** Alice  \n"
        "**Branch:** `main`\n\n---\n",
        encoding="utf-8",
    )

    res = client.get("/api/metrics/Owner_repo")
    body = res.json()
    assert body["commits_documented"] == 2
    assert body["contributors_tracked"] == 1
    assert body["contributors"] == ["Alice"]
