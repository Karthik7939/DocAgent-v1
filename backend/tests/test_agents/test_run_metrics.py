"""
tests/test_agents/test_run_metrics.py
----------------------------------------
Unit tests for agents/coordinator/run_metrics.py

Tests:
- compute_run_metrics derives every field correctly from SharedMemory
- faithfulness_score/notes pass through from ValidationReport unchanged
- test_coverage_ratio handles zero source files without dividing by zero
- write_run_metrics writes valid JSON to workflow.output_directory
- write_run_metrics no-ops (doesn't raise) when output_directory is unset
"""

import json

from agents.coordinator.run_metrics import compute_run_metrics, write_run_metrics
from agents.memory.shared_memory import (
    SharedMemory, ValidationReport, RepositoryStatistics,
    RepositoryMetadata, WorkflowMetadata, GeneratedDocumentation,
)


def _make_memory(**overrides) -> SharedMemory:
    mem = SharedMemory()
    mem.validation = ValidationReport(
        quality_score=87.345,
        faithfulness_score=91.678,
        faithfulness_notes="None",
    )
    mem.metadata = RepositoryMetadata(
        statistics=RepositoryStatistics(test_files=6, source_files=24)
    )
    mem.documentation = GeneratedDocumentation(
        file_docs={"README.md": "# hi", "ARCHITECTURE.md": "# arch", "EMPTY.md": ""}
    )
    mem.workflow = WorkflowMetadata(workflow_id="wf-123", output_directory=overrides.get("output_directory", ""))
    return mem


class TestComputeRunMetrics:

    def test_quality_score_rounded(self):
        metrics = compute_run_metrics(_make_memory(), total_execution_time=60.0)
        assert metrics["quality_score"] == 87.3

    def test_faithfulness_score_rounded(self):
        metrics = compute_run_metrics(_make_memory(), total_execution_time=60.0)
        assert metrics["faithfulness_score"] == 91.7

    def test_faithfulness_notes_passthrough(self):
        metrics = compute_run_metrics(_make_memory(), total_execution_time=60.0)
        assert metrics["faithfulness_notes"] == "None"

    def test_documents_generated_excludes_empty(self):
        """EMPTY.md has blank content and should not count."""
        metrics = compute_run_metrics(_make_memory(), total_execution_time=60.0)
        assert metrics["documents_generated"] == 2

    def test_average_time_per_document(self):
        metrics = compute_run_metrics(_make_memory(), total_execution_time=60.0)
        assert metrics["average_time_per_document_seconds"] == 30.0

    def test_test_coverage_ratio(self):
        metrics = compute_run_metrics(_make_memory(), total_execution_time=60.0)
        assert metrics["test_coverage_ratio"] == 0.25  # 6/24

    def test_test_coverage_ratio_no_source_files(self):
        mem = _make_memory()
        mem.metadata.statistics.source_files = 0
        metrics = compute_run_metrics(mem, total_execution_time=60.0)
        assert metrics["test_coverage_ratio"] == 0.0

    def test_generation_time_seconds(self):
        metrics = compute_run_metrics(_make_memory(), total_execution_time=123.456)
        assert metrics["generation_time_seconds"] == 123.46


class TestWriteRunMetrics:

    def test_writes_valid_json(self, tmp_path):
        mem = _make_memory(output_directory=str(tmp_path))
        write_run_metrics(mem, total_execution_time=45.0)

        metrics_file = tmp_path / "metrics.json"
        assert metrics_file.is_file()
        data = json.loads(metrics_file.read_text(encoding="utf-8"))
        assert data["quality_score"] == 87.3
        assert data["faithfulness_score"] == 91.7
        assert data["generation_time_seconds"] == 45.0

    def test_noop_when_output_directory_unset(self, tmp_path):
        mem = _make_memory(output_directory="")
        # Should not raise even though nothing gets written.
        write_run_metrics(mem, total_execution_time=45.0)
        assert not (tmp_path / "metrics.json").exists()
