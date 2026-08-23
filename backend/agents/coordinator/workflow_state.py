"""
agents/coordinator/workflow_state.py
--------------------------------------
Workflow State — runtime execution tracker for the Coordinator.

This module contains two distinct types:

  AgentWorkflowState — a dataclass that tracks lifecycle, timing, retry
    counts, and audit logs for one workflow run. This is populated by the
    Coordinator and is separate from SharedMemory so orchestration metadata
    never mixes with agent output.

  PipelineState — a TypedDict used as the LangGraph StateGraph schema.
    Every node in the graph receives this state and returns a partial
    dict update. LangGraph merges returned dicts into the current state
    (updated keys replace, untouched keys remain).

No business logic. No AI logic. Pure data containers.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

try:
    from typing import TypedDict          # Python 3.8+
except ImportError:                       # pragma: no cover
    from typing_extensions import TypedDict


# ---------------------------------------------------------------------------
# Allowed workflow status values  (SRS Part 2, Section 9)
# ---------------------------------------------------------------------------

class AgentWorkflowStatus(str, Enum):
    """
    Allowed lifecycle states for an agent workflow execution.

    Transitions (SRS Part 2, Section 22):
      CREATED → INITIALIZED → RUNNING → COMPLETED
      RUNNING → FAILED
      RUNNING → WAITING → RUNNING
    """

    CREATED = "CREATED"
    INITIALIZED = "INITIALIZED"
    RUNNING = "RUNNING"
    WAITING = "WAITING"
    VALIDATING = "VALIDATING"
    REVISING = "REVISING"
    SYNCING = "SYNCING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


# ---------------------------------------------------------------------------
# Known agent names — used to populate current_agent field
# ---------------------------------------------------------------------------

class AgentName(str, Enum):
    """Names of all agents in execution order."""

    PREPROCESSING = "PreprocessingAgent"
    UNDERSTANDING = "UnderstandingAgent"
    DOCUMENTATION = "DocumentationAgent"
    VALIDATION = "ValidationAgent"
    REVISION = "RevisionAgent"
    SYNC = "SyncAgent"


# ---------------------------------------------------------------------------
# Workflow State dataclass
# ---------------------------------------------------------------------------

@dataclass
class AgentWorkflowState:
    """
    Tracks the complete execution state of a single agent workflow run.

    This object is created by the Coordinator at workflow initialization
    and updated after every agent execution.

    Attributes:
        workflow_id:        UUID string uniquely identifying this run.
        repository_name:    Full repository name, e.g. 'owner/repo'.
        repository_path:    Local filesystem path to the cloned repository.
        branch:             Branch that triggered the workflow.
        commit_sha:         HEAD commit SHA.
        status:             Current lifecycle status.
        current_agent:      Name of the agent currently executing (or last executed).
        completed_agents:   Ordered list of agent names that have finished successfully.
        failed_agent:       Name of the agent that caused a failure, if any.
        start_time:         UTC datetime when the workflow was started.
        end_time:           UTC datetime when the workflow finished (success or failure).
        execution_time:     Total elapsed seconds from start to finish.
        retry_count:        Total number of agent retry attempts across all agents.
        logs:               Ordered list of human-readable log messages.
        agent_durations:    Per-agent execution time in seconds.
    """

    workflow_id: str
    repository_name: str
    repository_path: str
    branch: str
    commit_sha: str

    # Lifecycle
    status: AgentWorkflowStatus = AgentWorkflowStatus.CREATED
    current_agent: str = ""
    completed_agents: list[str] = field(default_factory=list)
    failed_agent: Optional[str] = None

    # Timing
    start_time: datetime = field(default_factory=datetime.utcnow)
    end_time: Optional[datetime] = None
    execution_time: float = 0.0

    # Retry tracking
    retry_count: int = 0

    # Audit log
    logs: list[str] = field(default_factory=list)

    # Per-agent timing
    agent_durations: dict[str, float] = field(default_factory=dict)

    # ---------------------------------------------------------------------------
    # Convenience mutators
    # ---------------------------------------------------------------------------

    def transition_to(self, new_status: AgentWorkflowStatus) -> None:
        """Transition the workflow to a new lifecycle status.

        Args:
            new_status: The target status to transition to.
        """
        self.status = new_status

    def set_current_agent(self, agent_name: str) -> None:
        """Record the agent that is currently executing.

        Args:
            agent_name: The name of the agent now running.
        """
        self.current_agent = agent_name

    def mark_agent_completed(self, agent_name: str, duration: float) -> None:
        """Record a successfully completed agent.

        Args:
            agent_name: Name of the agent that finished.
            duration:   How long the agent took in seconds.
        """
        if agent_name not in self.completed_agents:
            self.completed_agents.append(agent_name)
        self.agent_durations[agent_name] = duration

    def mark_failed(self, agent_name: str, reason: str) -> None:
        """Mark the workflow as failed due to a specific agent.

        Args:
            agent_name: Name of the agent that caused the failure.
            reason:     Human-readable failure description.
        """
        self.failed_agent = agent_name
        self.status = AgentWorkflowStatus.FAILED
        self.add_log(f"[FAILED] Agent={agent_name}  Reason={reason}")

    def mark_completed(self) -> None:
        """Mark the workflow as successfully completed and record end time."""
        self.status = AgentWorkflowStatus.COMPLETED
        self.end_time = datetime.utcnow()
        self.execution_time = (self.end_time - self.start_time).total_seconds()

    def increment_retry(self) -> None:
        """Increment the global retry counter by one."""
        self.retry_count += 1

    def add_log(self, message: str) -> None:
        """Append a log message with a UTC timestamp prefix.

        Args:
            message: Human-readable log entry.
        """
        timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        self.logs.append(f"{timestamp} | {message}")

    # ---------------------------------------------------------------------------
    # Serialisation
    # ---------------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Serialise the workflow state to a plain dictionary.

        Returns:
            dict: JSON-serialisable representation of the workflow state.
        """
        return {
            "workflow_id": self.workflow_id,
            "repository_name": self.repository_name,
            "repository_path": self.repository_path,
            "branch": self.branch,
            "commit_sha": self.commit_sha,
            "status": self.status.value,
            "current_agent": self.current_agent,
            "completed_agents": self.completed_agents,
            "failed_agent": self.failed_agent,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "execution_time": self.execution_time,
            "retry_count": self.retry_count,
            "agent_durations": self.agent_durations,
            "logs": self.logs,
        }


# ---------------------------------------------------------------------------
# LangGraph Pipeline State
# ---------------------------------------------------------------------------

class PipelineState(TypedDict, total=False):
    """
    LangGraph StateGraph schema — the shared state that flows through every node.

    Each node receives the current PipelineState and returns a *partial* dict
    with only the keys it updates. LangGraph merges these updates so untouched
    keys are preserved automatically.

    Attributes:
        workflow_id:          UUID for this pipeline run.
        repository_name:      Full repo name (owner/repo).
        repository_path:      Local filesystem path to the cloned repository.
        branch:               Git branch that triggered the workflow.
        commit_sha:           HEAD commit SHA.
        shared_memory:        The SharedMemory object — populated progressively
                              as agents execute. Typed as Any to avoid circular
                              imports; runtime type is SharedMemory.
        agent_workflow_state: The AgentWorkflowState object tracking lifecycle,
                              timing, retries, and logs. Typed as Any for the
                              same reason.
        revision_cycles:      Number of validation→revision cycles completed.
                              Incremented by the revision node; used by the
                              conditional router to prevent infinite loops.
        error:                Non-None string if the pipeline has failed.
                              Nodes check this first and short-circuit if set.
    """

    workflow_id: str
    repository_name: str
    repository_path: str
    branch: str
    commit_sha: str
    shared_memory: Any          # agents.memory.shared_memory.SharedMemory
    agent_workflow_state: Any   # AgentWorkflowState
    revision_cycles: int
    error: Optional[str]
