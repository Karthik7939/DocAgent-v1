"""
agents/coordinator/coordinator.py
-----------------------------------
Coordinator Agent — LangGraph-powered orchestrator.

The 6-agent documentation pipeline is modelled as a LangGraph StateGraph.
Each agent becomes a node; edges encode the fixed execution order.
A conditional edge after the validation node implements the
validation → revision → re-validation cycle.

Pipeline graph:
    preprocessing → understanding → documentation → validation
                                                         │
                                           ┌─────────────┤
                                           │             │
                                     (FAILED +      (PASSED or
                                     cycles ≥ max)  cycles < max)
                                           │             │
                                          END         revision
                                                          │
                                                (back to) validation
                                                      │
                                                   (PASSED)
                                                      │
                                                    sync → END

Public interface is unchanged:
    coordinator.start_workflow(...) → WorkflowSummary

The Coordinator MUST NOT:
  - Call LLMs directly.
  - Parse repository files.
  - Generate documentation.
  - Access the vector database.
  - Read repository files.
  - Save markdown files.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Optional, cast

from langgraph.graph import StateGraph, END

from agents.coordinator.workflow_state import (
    AgentWorkflowState,
    AgentWorkflowStatus,
    AgentName,
    PipelineState,
)
from agents.memory.shared_memory import (
    SharedMemory,
    RepositoryInfo,
    WorkflowMetadata,
)
from utils.helpers import generate_uuid, generate_timestamp

logger = logging.getLogger(__name__)

# Maximum retry attempts per agent before the workflow is marked FAILED.
MAX_RETRIES: int = 3


# ---------------------------------------------------------------------------
# Agent Result Contract
# ---------------------------------------------------------------------------

@dataclass
class AgentResult:
    """
    Standardised result that every agent must return to the Coordinator.

    Attributes:
        success:        True if the agent completed without a critical error.
        message:        Human-readable summary of what the agent did.
        execution_time: How long the agent took in seconds.
        warnings:       Non-critical issues the agent encountered.
        errors:         Critical problems that caused the agent to fail.
        recoverable:    If False, the Coordinator must not retry this agent.
    """

    success: bool
    message: str
    execution_time: float = 0.0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    recoverable: bool = True


# ---------------------------------------------------------------------------
# Workflow Summary
# ---------------------------------------------------------------------------

@dataclass
class WorkflowSummary:
    """
    Final summary returned by the Coordinator after workflow completion.

    Attributes:
        workflow_id:          UUID of the completed workflow.
        repository_name:      Full repository name.
        status:               Final workflow status string.
        completed_agents:     List of agents that finished successfully.
        failed_agent:         Agent name that caused failure, if any.
        total_execution_time: Total duration in seconds.
        generated_documents:  Names of documents that were generated.
        error_message:        Failure reason, if applicable.
        agent_durations:      Per-agent execution times in seconds.
    """

    workflow_id: str
    repository_name: str
    status: str
    completed_agents: list[str]
    failed_agent: Optional[str]
    total_execution_time: float
    generated_documents: list[str]
    error_message: Optional[str]
    agent_durations: dict[str, float]

    def to_dict(self) -> dict:
        """Serialise the summary to a plain dictionary."""
        return {
            "workflow_id": self.workflow_id,
            "repository_name": self.repository_name,
            "status": self.status,
            "completed_agents": self.completed_agents,
            "failed_agent": self.failed_agent,
            "total_execution_time": self.total_execution_time,
            "generated_documents": self.generated_documents,
            "error_message": self.error_message,
            "agent_durations": self.agent_durations,
        }


# ---------------------------------------------------------------------------
# Coordinator — LangGraph-backed orchestrator
# ---------------------------------------------------------------------------

class Coordinator:
    """
    Central orchestrator for the Agentic AI Documentation Generation System.

    Internally builds and runs a LangGraph StateGraph. The public API
    (start_workflow) is identical to the previous implementation so no
    callers need to change.

    Usage::

        coordinator = Coordinator(
            preprocessing_agent=PreprocessingAgent(),
            understanding_agent=UnderstandingAgent(llm_client=llm),
            documentation_agent=DocumentationAgent(llm_client=llm),
            validation_agent=ValidationAgent(llm_client=llm),
            revision_agent=RevisionAgent(llm_client=llm),
            sync_agent=SyncAgent(output_dir="generated_docs"),
        )

        summary = coordinator.start_workflow(
            repository_name="owner/repo",
            repository_path="repositories/owner_repo",
            branch="main",
            commit_sha="abc123",
        )

    Args:
        preprocessing_agent:  Agent that scans and classifies the repository.
        understanding_agent:  Agent that performs semantic reasoning via LLM.
        documentation_agent:  Agent that generates Markdown documentation.
        validation_agent:     Agent that evaluates documentation quality.
        revision_agent:       Agent that automatically corrects issues.
        sync_agent:           Agent that saves documentation to disk.
        max_retries:          Maximum retry attempts per recoverable failure.
        max_revision_cycles:  Maximum validation→revision cycles before FAILED.
    """

    def __init__(
        self,
        preprocessing_agent,
        understanding_agent,
        documentation_agent,
        validation_agent,
        revision_agent,
        sync_agent,
        max_retries: int = MAX_RETRIES,
        max_revision_cycles: int = 2,
    ) -> None:
        self._preprocessing = preprocessing_agent
        self._understanding = understanding_agent
        self._documentation = documentation_agent
        self._validation = validation_agent
        self._revision = revision_agent
        self._sync = sync_agent
        self._max_retries = max_retries
        self._max_revision_cycles = max_revision_cycles

        # Compile the LangGraph StateGraph once at construction time.
        self._graph = self._build_graph()
        logger.info(
            "Coordinator: LangGraph pipeline compiled "
            "(max_retries=%d, max_revision_cycles=%d)",
            max_retries, max_revision_cycles,
        )

    # ------------------------------------------------------------------
    # Graph construction
    # ------------------------------------------------------------------

    def _build_graph(self):
        """
        Build and compile the LangGraph StateGraph.

        Nodes map to agent execution steps. Edges encode the fixed
        execution order. A conditional edge after validation routes to
        revision, sync, or END (failed) depending on quality score and
        the number of revision cycles already attempted.

        Returns:
            CompiledGraph: Ready-to-invoke LangGraph graph.
        """
        builder = StateGraph(PipelineState)

        # --- Register nodes (one per agent) ---
        builder.add_node("preprocessing", self._preprocessing_node)
        builder.add_node("understanding",  self._understanding_node)
        builder.add_node("planner",        self._planner_node)
        builder.add_node("documentation",  self._documentation_node)
        builder.add_node("validation",     self._validation_node)
        builder.add_node("revision",       self._revision_node)
        builder.add_node("sync",           self._sync_node)

        # --- Entry point ---
        builder.set_entry_point("preprocessing")

        # --- Linear edges (fixed order) ---
        builder.add_edge("preprocessing", "understanding")
        builder.add_edge("understanding",  "planner")
        builder.add_edge("planner",        "documentation")
        builder.add_edge("documentation",  "validation")

        # --- Conditional edge: after validation ---
        # Router returns one of: "sync" | "revision" | "failed"
        builder.add_conditional_edges(
            "validation",
            self._validation_router,
            {
                "sync":     "sync",
                "revision": "revision",
                "failed":   END,
            },
        )

        # After revision → re-validate
        builder.add_edge("revision", "validation")

        # After successful sync → pipeline complete
        builder.add_edge("sync", END)

        return builder.compile()

    # ------------------------------------------------------------------
    # Routing function (validation conditional edge)
    # ------------------------------------------------------------------

    def _validation_router(self, state: PipelineState) -> str:
        """
        Decide the next step after the validation node runs.

        Decision tree:
          - Error flag is set           → "failed"  (stop immediately)
          - Validation PASSED / WARNING  → "sync"    (proceed to write docs)
          - Validation FAILED + cycles < max → "revision" (attempt fix)
          - Validation FAILED + cycles ≥ max → "failed"  (give up)

        Args:
            state: Current pipeline state after validation node.

        Returns:
            str: One of "sync", "revision", or "failed".
        """
        if state.get("error"):
            logger.warning("Validation router: error flag set → routing to failed")
            return "failed"

        memory: SharedMemory = state["shared_memory"]
        validation_status: str = memory.validation.validation_status
        revision_cycles: int  = state.get("revision_cycles", 0)

        logger.info(
            "Validation router: status=%s  revision_cycles=%d/%d",
            validation_status, revision_cycles, self._max_revision_cycles,
        )

        if validation_status in ("PASSED", "PASSED_WITH_WARNINGS"):
            return "sync"

        if revision_cycles < self._max_revision_cycles:
            return "revision"

        # Exhausted all revision cycles
        logger.error(
            "Validation router: max revision cycles (%d) exhausted → failed",
            self._max_revision_cycles,
        )
        wf_state: AgentWorkflowState = state["agent_workflow_state"]
        reason = (
            f"Validation FAILED after {self._max_revision_cycles} revision cycle(s). "
            f"Score: {memory.validation.quality_score:.1f}"
        )
        wf_state.mark_failed(AgentName.VALIDATION.value, reason)
        return "failed"

    # ------------------------------------------------------------------
    # Node implementations
    # ------------------------------------------------------------------

    def _preprocessing_node(self, state: PipelineState) -> dict:
        """LangGraph node: run PreprocessingAgent."""
        return self._run_node(state, AgentName.PREPROCESSING, self._preprocessing)

    def _understanding_node(self, state: PipelineState) -> dict:
        """LangGraph node: run UnderstandingAgent."""
        return self._run_node(state, AgentName.UNDERSTANDING, self._understanding)

    def _planner_node(self, state: PipelineState) -> dict:
        """LangGraph node: run DocumentationPlanningAgent."""
        from agents.documentation.planner_agent import DocumentationPlanningAgent
        planner = DocumentationPlanningAgent()
        return self._run_node(state, AgentName.PLANNER, planner)

    def _documentation_node(self, state: PipelineState) -> dict:
        """LangGraph node: run DocumentationAgent."""
        return self._run_node(state, AgentName.DOCUMENTATION, self._documentation)

    def _validation_node(self, state: PipelineState) -> dict:
        """LangGraph node: run ValidationAgent."""
        return self._run_node(state, AgentName.VALIDATION, self._validation)

    def _revision_node(self, state: PipelineState) -> dict:
        """LangGraph node: run RevisionAgent and increment revision cycle counter."""
        updates = self._run_node(state, AgentName.REVISION, self._revision)
        # Increment the revision cycle counter in the returned update dict
        updates["revision_cycles"] = state.get("revision_cycles", 0) + 1
        return updates

    def _sync_node(self, state: PipelineState) -> dict:
        """LangGraph node: run SyncAgent."""
        return self._run_node(state, AgentName.SYNC, self._sync)

    # ------------------------------------------------------------------
    # Generic node runner (with retry logic)
    # ------------------------------------------------------------------

    def _run_node(
        self,
        state: PipelineState,
        agent_name: AgentName,
        agent,
    ) -> dict:
        """
        Execute a single agent inside a LangGraph node with retry logic.

        Short-circuits immediately if the error flag is already set in
        the current state (prevents cascading failures).

        Retries up to self._max_retries times for recoverable failures.
        On non-recoverable failure or exhausted retries, sets the error
        flag in the returned state update.

        Args:
            state:      Current pipeline state from LangGraph.
            agent_name: Enum identifying this agent (for logging/tracking).
            agent:      Agent instance whose .run(shared_memory) is called.

        Returns:
            dict: Partial state update dict for LangGraph to merge.
        """
        # Short-circuit: a previous node already failed
        if state.get("error"):
            logger.debug(
                "Skipping %s — error flag already set: %s",
                agent_name.value, state.get("error"),
            )
            return {}

        shared_memory: SharedMemory       = state["shared_memory"]
        wf_state: AgentWorkflowState      = state["agent_workflow_state"]

        # Update orchestration tracking
        wf_state.set_current_agent(agent_name.value)
        wf_state.transition_to(AgentWorkflowStatus.RUNNING)
        shared_memory.workflow.current_agent  = agent_name.value
        shared_memory.workflow.current_status = AgentWorkflowStatus.RUNNING.value

        logger.info("LangGraph node: executing %s", agent_name.value)
        wf_state.add_log(f"Executing {agent_name.value}")

        last_result: Optional[AgentResult] = None

        for attempt in range(1, self._max_retries + 1):
            start = time.monotonic()
            try:
                last_result = agent.run(shared_memory)
                if last_result is None:
                    last_result = AgentResult(success=True, message=f"{agent_name.value} completed", execution_time=time.monotonic() - start)
                else:
                    last_result.execution_time = time.monotonic() - start
            except Exception as exc:
                duration = time.monotonic() - start
                logger.exception(
                    "Unexpected exception in %s (attempt %d): %s",
                    agent_name.value, attempt, exc,
                )
                last_result = AgentResult(
                    success=False,
                    message=str(exc),
                    execution_time=duration,
                    errors=[str(exc)],
                    recoverable=False,
                )

            if last_result.success:
                # ✓ Agent succeeded
                wf_state.mark_agent_completed(
                    agent_name.value, last_result.execution_time
                )
                wf_state.add_log(
                    f"{agent_name.value} completed in {last_result.execution_time:.2f}s"
                )
                logger.info(
                    "%s completed in %.2fs", agent_name.value, last_result.execution_time
                )
                return {
                    "shared_memory":      shared_memory,
                    "agent_workflow_state": wf_state,
                    "error":              None,
                }

            # ✗ Agent failed for this attempt
            logger.warning(
                "%s failed (attempt %d/%d): %s",
                agent_name.value, attempt, self._max_retries, last_result.message,
            )
            wf_state.add_log(
                f"{agent_name.value} failed "
                f"(attempt {attempt}/{self._max_retries}): {last_result.message}"
            )
            wf_state.increment_retry()

            if not last_result.recoverable:
                logger.error(
                    "%s is non-recoverable — stopping retries", agent_name.value
                )
                break  # Don't bother retrying

        # All retries exhausted (or non-recoverable failure)
        reason = (
            f"{agent_name.value} failed: {last_result.message}"
            if last_result else f"{agent_name.value} failed: unknown error"
        )
        wf_state.mark_failed(agent_name.value, reason)
        logger.error("Agent permanently failed: %s", reason)

        return {
            "shared_memory":      shared_memory,
            "agent_workflow_state": wf_state,
            "error":              reason,
        }

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def start_workflow(
        self,
        repository_name: str,
        repository_path: str,
        branch: str,
        commit_sha: str,
        workflow_id: Optional[str] = None,
        added_files: Optional[list] = None,
        modified_files: Optional[list] = None,
        author: str = "",
        push_timestamp: str = "",
        context_package=None,
    ) -> WorkflowSummary:
        """
        Execute the complete documentation generation pipeline.

        Builds the initial LangGraph state, invokes the compiled graph,
        waits for completion, and returns a WorkflowSummary.

        This is the only public method on the Coordinator.

        Args:
            repository_name:  Full repository name, e.g. 'owner/repo'.
            repository_path:  Local path to the cloned repository.
            branch:           Branch that was pushed to.
            commit_sha:       HEAD commit SHA.
            workflow_id:      Optional UUID; generated if not provided.
            added_files:      Files added in the triggering push event.
            modified_files:   Files modified in the triggering push event.
            author:           GitHub username of the developer who pushed.
            push_timestamp:   ISO-8601 timestamp of the push event.
            context_package:  Optional ContextPackage from a prior RAGPipeline
                              run. When provided it is stored in SharedMemory
                              so UnderstandingAgent can use it without running
                              a second retrieval pass.

        Returns:
            WorkflowSummary: Final result containing status, documents, and timing.
        """
        wf_id = workflow_id or generate_uuid()
        logger.info(
            "Workflow started: id=%s  repo=%s  branch=%s",
            wf_id, repository_name, branch,
        )

        # --- Build SharedMemory ---
        shared_memory = self._initialize_memory(
            workflow_id=wf_id,
            repository_name=repository_name,
            repository_path=repository_path,
            branch=branch,
            commit_sha=commit_sha,
            added_files=added_files or [],
            modified_files=modified_files or [],
            author=author,
            push_timestamp=push_timestamp,
        )

        # Attach the pre-computed RAG context package when available.
        # UnderstandingAgent reads shared_memory.rag_context_package to use
        # retrieved code context without running a second pipeline call.
        if context_package is not None:
            shared_memory.rag_context_package = context_package
            logger.info(
                "Coordinator: RAG context package attached to shared memory "
                "(%d retrieved chunk(s))",
                getattr(
                    getattr(context_package, "metadata", None),
                    "total_retrieved_chunks",
                    0,
                ),
            )

        # --- Build AgentWorkflowState ---
        wf_state = AgentWorkflowState(
            workflow_id=wf_id,
            repository_name=repository_name,
            repository_path=repository_path,
            branch=branch,
            commit_sha=commit_sha,
        )
        wf_state.transition_to(AgentWorkflowStatus.INITIALIZED)
        wf_state.add_log("Workflow initialised")
        logger.info("Workflow initialised: id=%s", wf_id)

        # --- Build initial LangGraph state ---
        initial_state: PipelineState = {
            "workflow_id":          wf_id,
            "repository_name":      repository_name,
            "repository_path":      repository_path,
            "branch":               branch,
            "commit_sha":           commit_sha,
            "shared_memory":        shared_memory,
            "agent_workflow_state": wf_state,
            "revision_cycles":      0,
            "error":                None,
        }

        # --- Run the LangGraph graph ---
        try:
            logger.info("LangGraph: starting graph execution (id=%s)", wf_id)
            # self._graph.invoke() returns a plain dict at the type level
            # (LangGraph's CompiledGraph.invoke is not generic over our
            # TypedDict); cast is safe here because every node merges back
            # into the same PipelineState-shaped dict the graph was seeded
            # with in initial_state above.
            final_state: PipelineState = cast(
                PipelineState, self._graph.invoke(initial_state)
            )
            logger.info("LangGraph: graph execution complete (id=%s)", wf_id)
        except Exception as exc:
            logger.exception("LangGraph execution raised an exception: %s", exc)
            wf_state.mark_failed("Coordinator", str(exc))
            final_state = {
                **initial_state,
                "error":              str(exc),
                "agent_workflow_state": wf_state,
            }

        # --- Extract final objects from state ---
        final_memory: SharedMemory = final_state.get(
            "shared_memory", shared_memory
        )
        final_wf_state: AgentWorkflowState = final_state.get(
            "agent_workflow_state", wf_state
        )

        # Mark completed if no error flag
        if not final_state.get("error"):
            final_wf_state.mark_completed()

        logger.info(
            "Workflow finished: id=%s  status=%s  duration=%.2fs",
            wf_id,
            final_wf_state.status.value,
            final_wf_state.execution_time,
        )

        return self._build_summary(final_wf_state, final_memory)

    # ------------------------------------------------------------------
    # Initialisation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _initialize_memory(
        workflow_id: str,
        repository_name: str,
        repository_path: str,
        branch: str,
        commit_sha: str,
        added_files: list,
        modified_files: list,
        author: str,
        push_timestamp: str,
    ) -> SharedMemory:
        """
        Create and seed the SharedMemory object before the graph runs.

        Populates the repository identity and workflow metadata sections
        so agents can read them from the first node onward.

        Args:
            workflow_id:     UUID for this run.
            repository_name: Full repository name.
            repository_path: Local path.
            branch:          Branch name.
            commit_sha:      HEAD commit SHA.
            added_files:     Files added in the push.
            modified_files:  Files modified in the push.
            author:          GitHub username of the pusher.
            push_timestamp:  ISO-8601 timestamp of the push event.

        Returns:
            SharedMemory: Seeded, ready for agents to use.
        """
        memory = SharedMemory()

        memory.repository = RepositoryInfo(
            name=repository_name.split("/")[-1],
            full_name=repository_name,
            path=repository_path,
            owner=repository_name.split("/")[0] if "/" in repository_name else "",
            branch=branch,
            commit_sha=commit_sha,
            clone_timestamp=generate_timestamp(),
            added_files=added_files,
            modified_files=modified_files,
            author=author,
            push_timestamp=push_timestamp,
        )

        memory.workflow = WorkflowMetadata(
            workflow_id=workflow_id,
            current_agent="",
            current_status=AgentWorkflowStatus.INITIALIZED.value,
        )

        logger.info(
            "Shared memory seeded: id=%s  added=%d  modified=%d  author=%s",
            workflow_id, len(added_files), len(modified_files), author or "unknown",
        )
        return memory

    # ------------------------------------------------------------------
    # Finalisation
    # ------------------------------------------------------------------

    @staticmethod
    def _build_summary(
        wf_state: AgentWorkflowState,
        memory: SharedMemory,
    ) -> WorkflowSummary:
        """
        Build the final WorkflowSummary from the completed state objects.

        Args:
            wf_state: Final workflow state after graph execution.
            memory:   Final shared memory after graph execution.

        Returns:
            WorkflowSummary: Structured result for the caller.
        """
        generated = list(memory.documentation.all_documents().keys())

        error_msg: Optional[str] = None
        if wf_state.status == AgentWorkflowStatus.FAILED:
            error_msg = (
                f"Failed at {wf_state.failed_agent}"
                if wf_state.failed_agent
                else "Unknown failure"
            )

        summary = WorkflowSummary(
            workflow_id=wf_state.workflow_id,
            repository_name=wf_state.repository_name,
            status=wf_state.status.value,
            completed_agents=wf_state.completed_agents,
            failed_agent=wf_state.failed_agent,
            total_execution_time=wf_state.execution_time,
            generated_documents=generated,
            error_message=error_msg,
            agent_durations=wf_state.agent_durations,
        )

        logger.info(
            "Workflow summary: id=%s  status=%s  docs=%d  duration=%.2fs",
            summary.workflow_id,
            summary.status,
            len(generated),
            summary.total_execution_time,
        )
        return summary


# ---------------------------------------------------------------------------
# Internal exception — kept for backward compatibility only
# ---------------------------------------------------------------------------

class _WorkflowFailedError(Exception):
    """
    Kept for backward compatibility.
    No longer raised internally — LangGraph handles failure routing via
    the error field in PipelineState and conditional edges.
    """
