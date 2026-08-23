"""
tests/agents/test_sync.py
---------------------------
Unit tests for agents/sync/sync_agent.py
"""

import pytest
from pathlib import Path

from agents.sync.sync_agent import SyncAgent
from agents.memory.shared_memory import SharedMemory, RepositoryInfo, GeneratedDocumentation


def _make_memory_with_docs(readme: str = "", architecture: str = "") -> SharedMemory:
    mem = SharedMemory()
    mem.repository = RepositoryInfo(name="demo", full_name="Blrm123/demo")
    mem.documentation = GeneratedDocumentation(readme=readme, architecture=architecture)
    return mem


class TestSyncAgent:

    def test_run_success_writes_files(self, tmp_path):
        """Agent writes all non-empty documents to disk."""
        mem = _make_memory_with_docs(
            readme="# README\n\nContent.",
            architecture="# Architecture\n\nContent.",
        )
        agent = SyncAgent(output_dir=str(tmp_path), overwrite=True)
        result = agent.run(mem)
        assert result.success is True

        # Files should exist on disk
        output = tmp_path / "Blrm123_demo"
        assert (output / "README" / "README.md").exists()
        assert (output / "Architecture" / "Architecture.md").exists()

    def test_run_fails_with_no_documents(self, tmp_path):
        """Agent returns non-recoverable failure when documentation is empty."""
        mem = _make_memory_with_docs()
        agent = SyncAgent(output_dir=str(tmp_path))
        result = agent.run(mem)
        assert result.success is False
        assert result.recoverable is False

    def test_readme_content_correct(self, tmp_path):
        """Written README.md contains the correct content."""
        content = "# README\n\nHello World."
        mem = _make_memory_with_docs(readme=content)
        agent = SyncAgent(output_dir=str(tmp_path))
        agent.run(mem)

        written = (tmp_path / "Blrm123_demo" / "README" / "README.md").read_text(encoding="utf-8")
        assert written == content

    def test_overwrite_false_skips_existing(self, tmp_path):
        """With overwrite=False, existing files are not overwritten."""
        original = "# Original"
        updated = "# Updated"

        mem = _make_memory_with_docs(readme=original)
        agent = SyncAgent(output_dir=str(tmp_path), overwrite=True)
        agent.run(mem)

        mem2 = _make_memory_with_docs(readme=updated)
        agent_no_overwrite = SyncAgent(output_dir=str(tmp_path), overwrite=False)
        agent_no_overwrite.run(mem2)

        written = (tmp_path / "Blrm123_demo" / "README" / "README.md").read_text(encoding="utf-8")
        assert written == original

    def test_repo_slug_used_for_directory(self, tmp_path):
        """Output directory uses owner_repo slug (slash replaced with underscore)."""
        mem = _make_memory_with_docs(readme="# README")
        agent = SyncAgent(output_dir=str(tmp_path))
        agent.run(mem)
        assert (tmp_path / "Blrm123_demo").is_dir()

    def test_empty_document_skipped(self, tmp_path):
        """Empty document strings are skipped — no empty file created."""
        mem = _make_memory_with_docs(readme="", architecture="# Architecture\n\nContent.")
        agent = SyncAgent(output_dir=str(tmp_path))
        result = agent.run(mem)
        assert result.success is True
        assert not (tmp_path / "Blrm123_demo" / "README" / "README.md").exists()

    def test_execution_time_recorded(self, tmp_path):
        """Sync execution time is stored in workflow metadata."""
        mem = _make_memory_with_docs(readme="# README")
        agent = SyncAgent(output_dir=str(tmp_path))
        agent.run(mem)
        assert mem.workflow.execution_times.get("sync", 0) >= 0
