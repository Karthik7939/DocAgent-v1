"""
tests/agents/test_preprocessing.py
-------------------------------------
Unit tests for agents/preprocessing/preprocessing_agent.py
"""

import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from agents.preprocessing.preprocessing_agent import (
    PreprocessingAgent,
    IGNORED_DIRECTORIES,
    EXTENSION_TO_LANGUAGE,
)
from agents.memory.shared_memory import SharedMemory, RepositoryInfo


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def agent():
    return PreprocessingAgent()


@pytest.fixture()
def fake_repo(tmp_path):
    """Create a minimal fake repository on disk."""
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.py").write_text("from fastapi import FastAPI\napp = FastAPI()")
    (tmp_path / "app" / "routes.py").write_text("from app.main import app")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_main.py").write_text("def test_smoke(): pass")
    (tmp_path / "requirements.txt").write_text("fastapi==0.115.6\nuvicorn==0.32.1")
    (tmp_path / "README.md").write_text("# Demo Project")
    (tmp_path / ".env.example").write_text("API_KEY=")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "main.cpython-312.pyc").write_bytes(b"")
    return tmp_path


@pytest.fixture()
def shared_memory(fake_repo):
    mem = SharedMemory()
    mem.repository = RepositoryInfo(
        name="demo",
        full_name="Blrm123/demo",
        path=str(fake_repo),
    )
    return mem


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPreprocessingAgent:

    def test_run_success(self, agent, shared_memory):
        """Agent returns success for a valid repository."""
        result = agent.run(shared_memory)
        assert result.success is True

    def test_run_invalid_path(self, agent):
        """Agent returns non-recoverable failure for missing path."""
        mem = SharedMemory()
        mem.repository = RepositoryInfo(path="/nonexistent/path/xyz")
        result = agent.run(mem)
        assert result.success is False
        assert result.recoverable is False

    def test_languages_detected(self, agent, shared_memory):
        """Python files are detected as Python."""
        agent.run(shared_memory)
        languages = [ls.language for ls in shared_memory.metadata.languages]
        assert "Python" in languages

    def test_framework_detected(self, agent, shared_memory):
        """FastAPI is detected from requirements.txt."""
        agent.run(shared_memory)
        assert "FastAPI" in shared_memory.metadata.frameworks

    def test_dependency_files_detected(self, agent, shared_memory):
        """requirements.txt is detected as a dependency file."""
        agent.run(shared_memory)
        dep_files = shared_memory.metadata.dependency_files
        assert any("requirements.txt" in f for f in dep_files)

    def test_dependencies_extracted(self, agent, shared_memory):
        """Dependency names are extracted from requirements.txt."""
        agent.run(shared_memory)
        deps = shared_memory.metadata.dependencies
        assert "fastapi" in deps

    def test_important_files_detected(self, agent, shared_memory):
        """README.md is in important files."""
        agent.run(shared_memory)
        important = shared_memory.metadata.important_files
        assert important.get("README.md") is True

    def test_entry_points_detected(self, agent, shared_memory):
        """main.py is detected as an entry point."""
        agent.run(shared_memory)
        entry_points = shared_memory.metadata.entry_points
        assert any("main.py" in ep for ep in entry_points)

    def test_directory_tree_generated(self, agent, shared_memory):
        """Directory tree is a non-empty string."""
        agent.run(shared_memory)
        tree = shared_memory.metadata.directory_tree
        assert isinstance(tree, str)
        assert len(tree) > 0

    def test_statistics_populated(self, agent, shared_memory):
        """Statistics contain at least 1 file."""
        agent.run(shared_memory)
        stats = shared_memory.metadata.statistics
        assert stats.total_files > 0

    def test_pycache_ignored(self, agent, shared_memory, fake_repo):
        """__pycache__ directory is excluded from results."""
        agent.run(shared_memory)
        tree = shared_memory.metadata.directory_tree
        assert "__pycache__" not in tree

    def test_test_files_classified(self, agent, shared_memory):
        """test_*.py files are classified as Test."""
        agent.run(shared_memory)
        classifications = shared_memory.metadata.file_classifications
        test_files = [f for f, cat in classifications.items() if cat == "Test"]
        assert len(test_files) > 0

    def test_configuration_files_detected(self, agent, shared_memory):
        """.env.example is detected as a configuration file."""
        agent.run(shared_memory)
        config_files = shared_memory.metadata.configuration_files
        assert any(".env.example" in f for f in config_files)
