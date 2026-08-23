"""
tests/agents/test_shared_memory.py
------------------------------------
Unit tests for agents/memory/shared_memory.py
"""

import pytest
from agents.memory.shared_memory import (
    SharedMemory,
    RepositoryInfo,
    RepositoryMetadata,
    RepositoryUnderstanding,
    GeneratedDocumentation,
    ValidationReport,
    RevisionHistory,
    WorkflowMetadata,
    LanguageStat,
    RepositoryStatistics,
    ModuleInfo,
    ServiceInfo,
    APIEndpoint,
)


class TestSharedMemory:

    def test_default_construction(self):
        """SharedMemory can be created with all defaults."""
        mem = SharedMemory()
        assert isinstance(mem.repository, RepositoryInfo)
        assert isinstance(mem.metadata, RepositoryMetadata)
        assert isinstance(mem.understanding, RepositoryUnderstanding)
        assert isinstance(mem.documentation, GeneratedDocumentation)
        assert isinstance(mem.validation, ValidationReport)
        assert isinstance(mem.revision, RevisionHistory)
        assert isinstance(mem.workflow, WorkflowMetadata)

    def test_repository_info_fields(self):
        """RepositoryInfo stores all identity fields."""
        repo = RepositoryInfo(
            name="demo",
            full_name="Blrm123/demo",
            path="repositories/Blrm123_demo",
            owner="Blrm123",
            branch="main",
            commit_sha="abc123",
        )
        assert repo.name == "demo"
        assert repo.owner == "Blrm123"
        assert repo.branch == "main"

    def test_generated_documentation_all_documents_empty(self):
        """all_documents() returns empty dict when no content is set."""
        docs = GeneratedDocumentation()
        assert docs.all_documents() == {}

    def test_generated_documentation_all_documents_partial(self):
        """all_documents() returns only non-empty fields."""
        docs = GeneratedDocumentation(readme="# Hello", architecture="")
        result = docs.all_documents()
        assert "README" in result
        assert "Architecture" not in result

    def test_generated_documentation_all_documents_full(self):
        """all_documents() returns all 8 document types when all are set."""
        docs = GeneratedDocumentation(
            readme="r", architecture="a", api="b",
            installation="i", developer_guide="d",
            folder_guide="f", workflow_guide="w",
            configuration_guide="c",
        )
        assert len(docs.all_documents()) == 8

    def test_language_stat_fields(self):
        """LanguageStat stores language, count, and percentage."""
        stat = LanguageStat(language="Python", file_count=10, percentage=80.0)
        assert stat.language == "Python"
        assert stat.percentage == 80.0

    def test_module_info_defaults(self):
        """ModuleInfo has sensible defaults."""
        m = ModuleInfo(name="API", responsibility="Handles HTTP routes")
        assert m.name == "API"
        assert m.dependencies == []

    def test_api_endpoint_fields(self):
        """APIEndpoint stores method, route, and purpose."""
        ep = APIEndpoint(method="POST", route="/webhook/github", purpose="Receive webhook")
        assert ep.method == "POST"
        assert ep.route == "/webhook/github"

    def test_validation_report_defaults(self):
        """ValidationReport initialises with empty collections."""
        vr = ValidationReport()
        assert vr.quality_score == 0.0
        assert vr.errors == []
        assert vr.warnings == []
