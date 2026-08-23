"""
tests/agents/test_coordinator.py
----------------------------------
Unit tests for agents/coordinator/coordinator.py and workflow_state.py
"""

import pytest
from unittest.mock import MagicMock, patch
from agents.coordinator.coordinator import Coordinator, AgentResult, WorkflowSummary
from agents.coordinator.workflow_state import AgentWorkflowState, AgentWorkflowStatus
from agents.memory.shared_memory import SharedMemory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _passing_agent():
    """Return a mock agent whose run() always returns success."""
    agent = MagicMock()
    agent.run.return_value = AgentResult(success=True, message="OK", execution_time=0.1)
    return agent


def _failing_agent(recoverable: bool = True):
    """Return a mock agent whose run() always returns failure."""
    agent = MagicMock()
    agent.run.return_value = AgentResult(
        success=False, message="Simulated failure",
        recoverable=recoverable, execution_time=0.0,
    )
    return agent


def _make_coordinator(**overrides):
    """Build a Coordinator with all-passing mock agents."""
    defaults = dict(
        preprocessing_agent=_passing_agent(),
        understanding_agent=_passing_agent(),
        documentation_agent=_passing_agent(),
        validation_agent=_passing_agent(),
        revision_agent=_passing_agent(),
        sync_agent=_passing_agent(),
        max_retries=2,
        max_revision_cycles=1,
    )
    defaults.update(overrides)
    return Coordinator(**defaults)


# ---------------------------------------------------------------------------
# WorkflowState tests
# ---------------------------------------------------------------------------

class TestAgentWorkflowState:

    def test_initial_status_created(self):
        state = AgentWorkflowState(
            workflow_id="test-id",
            repository_name="owner/repo",
            repository_path="/path",
            branch="main",
            commit_sha="abc",
        )
        assert state.status == AgentWorkflowStatus.CREATED

    def test_transition_to(self):
        state = AgentWorkflowState("id", "r", "p", "b", "s")
        state.transition_to(AgentWorkflowStatus.RUNNING)
        assert state.status == AgentWorkflowStatus.RUNNING

    def test_mark_agent_completed(self):
        state = AgentWorkflowState("id", "r", "p", "b", "s")
        state.mark_agent_completed("PreprocessingAgent", 1.5)
        assert "PreprocessingAgent" in state.completed_agents
        assert state.agent_durations["PreprocessingAgent"] == 1.5

    def test_mark_failed(self):
        state = AgentWorkflowState("id", "r", "p", "b", "s")
        state.mark_failed("UnderstandingAgent", "LLM timeout")
        assert state.status == AgentWorkflowStatus.FAILED
        assert state.failed_agent == "UnderstandingAgent"

    def test_mark_completed(self):
        state = AgentWorkflowState("id", "r", "p", "b", "s")
        state.mark_completed()
        assert state.status == AgentWorkflowStatus.COMPLETED
        assert state.end_time is not None
        assert state.execution_time >= 0

    def test_add_log(self):
        state = AgentWorkflowState("id", "r", "p", "b", "s")
        state.add_log("test message")
        assert any("test message" in log for log in state.logs)

    def test_to_dict_keys(self):
        state = AgentWorkflowState("id", "owner/repo", "/path", "main", "sha")
        d = state.to_dict()
        assert "workflow_id" in d
        assert "status" in d
        assert "completed_agents" in d


# ---------------------------------------------------------------------------
# Coordinator tests
# ---------------------------------------------------------------------------

class TestCoordinator:

    def test_successful_workflow_returns_completed(self):
        """All agents pass → status=COMPLETED."""
        # Validation agent must set validation_status=PASSED in shared memory
        val_agent = MagicMock()
        def val_run(mem):
            mem.validation.validation_status = "PASSED"
            mem.validation.quality_score = 90.0
            return AgentResult(success=True, message="OK", execution_time=0.1)
        val_agent.run.side_effect = val_run

        coord = _make_coordinator(validation_agent=val_agent)
        summary = coord.start_workflow("owner/repo", "repositories/owner_repo", "main", "abc")

        assert summary.status == AgentWorkflowStatus.COMPLETED.value
        assert summary.failed_agent is None

    def test_non_recoverable_failure_marks_failed(self):
        """Non-recoverable preprocessing failure → status=FAILED."""
        coord = _make_coordinator(
            preprocessing_agent=_failing_agent(recoverable=False)
        )
        summary = coord.start_workflow("owner/repo", "repositories/owner_repo", "main", "abc")
        assert summary.status == AgentWorkflowStatus.FAILED.value
        assert summary.failed_agent == "PreprocessingAgent"

    def test_retry_on_recoverable_failure(self):
        """Agent fails twice then succeeds on third attempt."""
        call_count = {"n": 0}

        agent = MagicMock()
        def sometimes_fail(mem):
            call_count["n"] += 1
            if call_count["n"] < 3:
                return AgentResult(success=False, message="retry", recoverable=True)
            return AgentResult(success=True, message="OK")

        agent.run.side_effect = sometimes_fail

        val_agent = MagicMock()
        def val_run(mem):
            mem.validation.validation_status = "PASSED"
            return AgentResult(success=True, message="OK")
        val_agent.run.side_effect = val_run

        coord = _make_coordinator(preprocessing_agent=agent, validation_agent=val_agent, max_retries=3)
        summary = coord.start_workflow("owner/repo", "repositories/owner_repo", "main", "abc")
        assert summary.status == AgentWorkflowStatus.COMPLETED.value
        assert call_count["n"] == 3

    def test_workflow_id_generated_if_not_provided(self):
        val_agent = MagicMock()
        def val_run(mem):
            mem.validation.validation_status = "PASSED"
            return AgentResult(success=True, message="OK")
        val_agent.run.side_effect = val_run

        coord = _make_coordinator(validation_agent=val_agent)
        summary = coord.start_workflow("owner/repo", "repositories/owner_repo", "main", "abc")
        assert summary.workflow_id != ""

    def test_summary_contains_expected_keys(self):
        val_agent = MagicMock()
        def val_run(mem):
            mem.validation.validation_status = "PASSED"
            return AgentResult(success=True, message="OK")
        val_agent.run.side_effect = val_run

        coord = _make_coordinator(validation_agent=val_agent)
        summary = coord.start_workflow("owner/repo", "repositories/owner_repo", "main", "abc")
        d = summary.to_dict()

        for key in ["workflow_id", "status", "completed_agents", "failed_agent",
                    "total_execution_time", "generated_documents"]:
            assert key in d
