"""
agents/understanding/understanding_agent.py
---------------------------------------------
Understanding Agent — semantic reasoning layer.

Responsibilities (SRS Part 4):
- Read repository metadata from SharedMemory.
- Optionally use the RAG service to retrieve relevant code context
  (rag_service=None skips retrieval; a future update will provide it).
- Query the LLM with retrieved context (or metadata-only context) via
  prompt templates.
- Parse structured LLM responses.
- Populate SharedMemory.understanding with:
    - Project summary and purpose
    - Architecture type
    - Module inventory
    - Service inventory
    - API inventory
    - Data flow
    - Dependency graph
    - Folder responsibilities
    - Coding style

This agent MUST NOT:
- Read repository files directly (only via RAG when configured).
- Generate markdown documentation.
- Save files to disk.
- Validate or revise documentation.
"""

import logging
import re
import time
from pathlib import Path
from typing import Optional

from agents.coordinator.coordinator import AgentResult
from agents.memory.shared_memory import (
    SharedMemory,
    RepositoryUnderstanding,
    ModuleInfo,
    ServiceInfo,
    APIEndpoint,
)
from prompts.understanding_prompt import (
    PROJECT_UNDERSTANDING_PROMPT,
    API_DISCOVERY_PROMPT,
    FOLDER_RESPONSIBILITY_PROMPT,
    DEPENDENCY_GRAPH_PROMPT,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Minimal retrieval result stub (used when RAG is not configured)
# ---------------------------------------------------------------------------

class _NoRagResult:
    """
    Lightweight stand-in for RetrievalResult when no RAG service is configured.

    Provides the same .context attribute so the rest of the agent code
    remains unchanged regardless of whether RAG is available.
    """

    def __init__(self, query: str) -> None:
        self.query = query
        self.chunks: list = []
        self.context = (
            f"[No RAG context available for: '{query}'. "
            "Reasoning from repository metadata only.]"
        )


class _PrecomputedRagResult:
    """
    Wraps a pre-computed ContextPackage (produced by RAGPipeline) and
    adapts it to the .context attribute contract that UnderstandingAgent
    expects from its _retrieve() calls.

    Unlike _NoRagResult, this object carries the actual retrieved code
    chunks. The context string is formatted once and reused for every
    query — this is intentional because the ContextPackage is already
    the best available retrieval result for the current commit.
    """

    def __init__(self, context_package) -> None:
        self.chunks = list(context_package.retrieval_results.results)
        self.context = self._format(context_package)

    @staticmethod
    def _format(context_package) -> str:
        """Format a ContextPackage into an LLM-ready context string."""
        lines: list[str] = []
        for item in context_package.retrieval_results.results:
            meta = item.chunk.metadata
            header = (
                f"[File: {meta.file_path}"
                f" | Lines: {meta.start_line}-{meta.end_line}"
                f" | Source: {item.retrieval_source.value}"
                f" | Rank: {item.rank}]"
            )
            if item.retrieval_reason:
                header += f"\n[Reason: {item.retrieval_reason}]"
            lines.append(header)
            lines.append(item.chunk.content)
            lines.append("---")
        if not lines:
            return "[RAG pipeline ran but retrieved no chunks for this commit.]"
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# LLM Client Protocol
# ---------------------------------------------------------------------------

class LLMClientProtocol:
    """
    Minimal interface that any LLM client must satisfy.

    The production implementation is LLMService (which now uses LangChain
    ChatGroq internally). The MockLLMClient in run_pipeline.py also satisfies
    this protocol for local testing without an API key.

    Example::

        class MyCustomClient:
            def generate(self, prompt: str) -> str:
                ...
    """

    def generate(self, prompt: str) -> str:
        """Send a prompt to the LLM and return the response text.

        Args:
            prompt: The complete prompt string including any context.

        Returns:
            str: Raw LLM response text.
        """
        raise NotImplementedError("Implement LLMClientProtocol.generate()")


# ---------------------------------------------------------------------------
# Understanding Agent
# ---------------------------------------------------------------------------

class UnderstandingAgent:
    """
    Performs semantic understanding of a repository using LLM (+ optional RAG).

    When a RAGService is provided the agent indexes the repository and
    retrieves relevant code chunks before each LLM call, giving the model
    grounding in actual source code. When rag_service=None the agent reasons
    purely from the metadata populated by the PreprocessingAgent — still
    useful but without code-level specifics.

    Args:
        rag_service: Optional RAGService instance for retrieval.
                     Pass None to skip RAG (metadata-only mode).
        llm_client:  Object implementing LLMClientProtocol.generate().
                     Accepts LLMService (LangChain-backed) or MockLLMClient.
    """

    def __init__(
        self,
        rag_service=None,
        llm_client: Optional[LLMClientProtocol] = None,
    ) -> None:
        self._rag = rag_service          # None → no RAG retrieval
        self._llm = llm_client
        self._precomputed: Optional[_PrecomputedRagResult] = None

    def run(self, shared_memory: SharedMemory) -> AgentResult:
        """
        Execute the full understanding pipeline.

        Reads:  shared_memory.repository, shared_memory.metadata
        Writes: shared_memory.understanding

        Args:
            shared_memory: The shared memory object.

        Returns:
            AgentResult: Success or failure result for the Coordinator.
        """
        start = time.monotonic()
        repo_path = shared_memory.repository.path
        repo_name = shared_memory.repository.full_name

        if not repo_path:
            return AgentResult(
                success=False,
                message="Repository path is empty in shared memory",
                recoverable=False,
            )

        logger.info("Understanding started: %s", repo_name)

        # ------------------------------------------------------------------ #
        # Priority 1: Use a pre-computed ContextPackage from RAGPipeline.
        # This is set by the Coordinator when GitHubService ran an incremental
        # RAG pipeline before the agent graph started.
        # ------------------------------------------------------------------ #
        if shared_memory.rag_context_package is not None:
            pkg = shared_memory.rag_context_package
            if getattr(pkg, "has_context", False):
                self._precomputed = _PrecomputedRagResult(pkg)
                logger.info(
                    "UnderstandingAgent: using pre-computed RAG context package "
                    "(%d chunk(s))",
                    len(self._precomputed.chunks),
                )
            else:
                logger.info(
                    "UnderstandingAgent: pre-computed RAG context package has no chunks — "
                    "falling back to rag_service or metadata-only mode"
                )

        # ------------------------------------------------------------------ #
        # Priority 2: Use the injected RAGService for on-demand retrieval.
        # Conditionally index repository into RAG if not already indexed.
        # ------------------------------------------------------------------ #
        # ------------------------------------------------------------------ #
        # Ensure RAGService indexes the full repository if needed
        # ------------------------------------------------------------------ #
        if self._rag is not None and repo_path:
            try:
                logger.info("Ensuring RAG indexing is complete for repo: %s", repo_path)
                self._rag.index_repository(repo_path)
            except Exception as exc:
                logger.warning("RAG indexing warning (continuing): %s", exc)

        try:
            understanding = self._build_understanding(shared_memory)
            shared_memory.understanding = understanding
            logger.info("Shared memory updated with repository understanding")

        except RuntimeError as exc:
            # Recoverable — e.g. temporary LLM timeout
            logger.warning("Understanding recoverable error: %s", exc)
            return AgentResult(
                success=False,
                message=str(exc),
                recoverable=True,
            )
        except Exception as exc:
            logger.exception("Understanding non-recoverable error: %s", exc)
            return AgentResult(
                success=False,
                message=str(exc),
                recoverable=False,
            )

        duration = time.monotonic() - start
        logger.info("Understanding completed in %.2fs: %s", duration, repo_name)
        return AgentResult(
            success=True,
            message="Understanding completed successfully",
            execution_time=duration,
        )

    # ------------------------------------------------------------------
    # Pipeline
    # ------------------------------------------------------------------

    def _build_understanding(self, shared_memory: SharedMemory) -> RepositoryUnderstanding:
        """
        Run all LLM queries and parse their responses.

        Args:
            shared_memory: Full shared memory (reads metadata).

        Returns:
            RepositoryUnderstanding: Populated semantic model.
        """
        meta = shared_memory.metadata
        repo = shared_memory.repository

        lang_str = ", ".join(ls.language for ls in meta.languages) or "Unknown"
        fw_str   = ", ".join(meta.frameworks) or "Unknown"
        repo_name = repo.full_name or repo.name

        understanding = RepositoryUnderstanding()

        # --- Project understanding ---
        ctx = self._retrieve(
            "project purpose architecture main core system application overview README feature functionality",
            repo_name=repo_name,
        )
        raw = self._ask_llm(PROJECT_UNDERSTANDING_PROMPT.format(
            repository_name=repo.full_name,
            branch=repo.branch,
            languages=lang_str,
            frameworks=fw_str,
            context=ctx.context,
        ))
        self._parse_project_understanding(raw, understanding)
        logger.info("Project understanding generated")

        # --- API discovery ---
        api_ctx = self._retrieve(
            "API endpoint route HTTP POST GET APIRouter router def predict upload FastAPI express Next.js handler request response pydantic BaseModel",
            repo_name=repo_name,
        )
        api_raw = self._ask_llm(API_DISCOVERY_PROMPT.format(
            repository_name=repo.full_name,
            frameworks=fw_str,
            context=api_ctx.context,
        ))
        parsed_apis = self._parse_apis(api_raw)
        static_apis = self._scan_static_routes(repo.path)

        # Merge LLM-discovered APIs and static-scanned APIs without duplicates
        seen_routes = set()
        combined_apis: list[APIEndpoint] = []

        for ep in parsed_apis + static_apis:
            key = f"{ep.method}:{ep.route}"
            if key not in seen_routes:
                seen_routes.add(key)
                combined_apis.append(ep)

        understanding.apis = combined_apis
        logger.info("API discovery completed: %d endpoint(s)", len(understanding.apis))

        # --- Folder responsibilities ---
        folder_ctx = self._retrieve(
            "folder directory structure package module organization responsibilities architecture layout",
            repo_name=repo_name,
        )
        folder_raw = self._ask_llm(FOLDER_RESPONSIBILITY_PROMPT.format(
            repository_name=repo.full_name,
            directory_tree=meta.directory_tree,
            context=folder_ctx.context,
        ))
        understanding.folder_responsibilities = self._parse_folder_responsibilities(folder_raw)
        logger.info(
            "Folder responsibilities mapped: %d folder(s)",
            len(understanding.folder_responsibilities),
        )

        # --- Dependency graph ---
        dep_ctx = self._retrieve(
            "import dependency service layer component relationship client helper database client",
            repo_name=repo_name,
        )
        modules_str = "; ".join(m.name for m in understanding.modules) or "Unknown"
        dep_raw = self._ask_llm(DEPENDENCY_GRAPH_PROMPT.format(
            repository_name=repo.full_name,
            modules=modules_str,
            context=dep_ctx.context,
        ))
        understanding.dependency_graph = self._parse_dependency_graph(dep_raw)
        logger.info("Dependency graph built")

        # --- Knowledge graph (lightweight summary) ---
        understanding.knowledge_graph = self._build_knowledge_graph(understanding)

        return understanding

    # ------------------------------------------------------------------
    # Retrieval (RAG or stub)
    # ------------------------------------------------------------------

    def _retrieve(self, query: str, repo_name: str = ""):
        """
        Retrieve code context for a query.

        Priority order:
          1. On-demand retrieval via the injected RAGService (performs semantic
             vector + BM25 search across the entire repository for the query).
          2. Pre-computed ContextPackage attached to SharedMemory (fallback if
             on-demand retrieval returns empty).
          3. Stub (_NoRagResult) when neither source is available.

        Args:
            query: Natural-language query string.
            repo_name: Full repository slug (e.g. 'owner/repo').

        Returns:
            _PrecomputedRagResult | _RetrievalResult | _NoRagResult:
            Object with .context and .chunks attributes.
        """
        # Priority 1 — on-demand RAGService retrieval across the full repo index
        if self._rag is not None:
            try:
                res = self._rag.retrieve(query, repository_name=repo_name)
                if res and getattr(res, "chunks", None) and len(res.chunks) > 0:
                    logger.info("UnderstandingAgent: topic RAG retrieval returned %d chunk(s) for query '%s'", len(res.chunks), query[:40])
                    return res
            except Exception as exc:
                logger.warning("RAGService topic retrieval failed for '%s': %s", query[:40], exc)

        # Priority 2 — pre-computed package fallback (commit-diff context)
        if self._precomputed is not None:
            logger.info("UnderstandingAgent: using pre-computed RAG fallback for query '%s'", query[:40])
            return self._precomputed

        # Priority 3 — metadata-only stub
        return _NoRagResult(query)

    # ------------------------------------------------------------------
    # LLM call
    # ------------------------------------------------------------------

    def _ask_llm(self, prompt: str) -> str:
        """
        Call the LLM and return the raw response text.

        Args:
            prompt: Complete prompt string including retrieved context.

        Returns:
            str: LLM response text.

        Raises:
            RuntimeError: On any LLM communication failure.
        """
        try:
            return self._llm.generate(prompt)
        except Exception as exc:
            logger.warning("LLM call failed: %s", exc)
            raise RuntimeError(f"LLM call failed: {exc}") from exc

    # ------------------------------------------------------------------
    # Response parsers
    # ------------------------------------------------------------------

    def _parse_project_understanding(
        self, raw: str, understanding: RepositoryUnderstanding
    ) -> None:
        """
        Parse the PROJECT_UNDERSTANDING_PROMPT response.

        Fills: summary, purpose, architecture, modules, services, data_flow,
               coding_style fields in-place.

        Args:
            raw:           Raw LLM response text.
            understanding: Object to populate.
        """
        sections = self._split_sections(raw)

        understanding.project_summary = sections.get("PROJECT_SUMMARY", "").strip()
        understanding.project_purpose = sections.get("PROJECT_PURPOSE", "").strip()
        understanding.architecture_type = (
            sections.get("ARCHITECTURE_TYPE", "Unknown").strip() or "Unknown"
        )

        # Modules: NAME | RESPONSIBILITY | DEPENDENCIES
        modules: list[ModuleInfo] = []
        for line in sections.get("MODULES", "").splitlines():
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 2 and parts[0]:
                modules.append(ModuleInfo(
                    name=parts[0],
                    responsibility=parts[1] if len(parts) > 1 else "",
                    dependencies=[d.strip() for d in parts[2].split(",")] if len(parts) > 2 else [],
                ))
        understanding.modules = modules

        # Services: NAME | PURPOSE | INPUTS | OUTPUTS
        services: list[ServiceInfo] = []
        for line in sections.get("SERVICES", "").splitlines():
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 2 and parts[0]:
                services.append(ServiceInfo(
                    name=parts[0],
                    purpose=parts[1] if len(parts) > 1 else "",
                    inputs=[i.strip() for i in parts[2].split(",")] if len(parts) > 2 else [],
                    outputs=[o.strip() for o in parts[3].split(",")] if len(parts) > 3 else [],
                ))
        understanding.services = services

        # Data flow: ordered steps
        understanding.data_flow = [
            line.strip()
            for line in sections.get("DATA_FLOW", "").splitlines()
            if line.strip()
        ]

        # Coding style
        understanding.coding_style = {
            "observations": sections.get("CODING_STYLE", "").strip()
        }

    def _parse_apis(self, raw: str) -> list[APIEndpoint]:
        """
        Parse the API_DISCOVERY_PROMPT response.

        Format: METHOD | ROUTE | PURPOSE | REQUEST_MODEL | RESPONSE_MODEL

        Args:
            raw: Raw LLM response text.

        Returns:
            list[APIEndpoint]: Parsed API endpoints.
        """
        if "NO_ENDPOINTS_FOUND" in raw:
            return []

        endpoints: list[APIEndpoint] = []
        for line in raw.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("```"):
                continue
            # Skip Markdown table separator rows like |---|---|
            if re.match(r"^\|?[\s\-:|]+\|?$", line):
                continue
            # Split by | and filter out empty elements caused by leading/trailing |
            parts = [p.strip() for p in line.split("|") if p.strip()]
            # Skip table header rows
            if parts and parts[0].upper() in ("METHOD", "HTTP METHOD", "VERB"):
                continue
            if len(parts) >= 3:
                endpoints.append(APIEndpoint(
                    method=parts[0].upper().replace("**", ""),
                    route=parts[1].replace("`", ""),
                    purpose=parts[2],
                    request_model=parts[3] if len(parts) > 3 else "",
                    response_model=parts[4] if len(parts) > 4 else "",
                ))
        return endpoints

    def _parse_folder_responsibilities(self, raw: str) -> dict[str, str]:
        """
        Parse the FOLDER_RESPONSIBILITY_PROMPT response.

        Format: FOLDER | PURPOSE | KEY_FILES | RELATIONSHIPS

        Args:
            raw: Raw LLM response text.

        Returns:
            dict[str, str]: folder → purpose mapping.
        """
        result: dict[str, str] = {}
        for line in raw.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("```"):
                continue
            if re.match(r"^\|?[\s\-:|]+\|?$", line):
                continue
            parts = [p.strip() for p in line.split("|") if p.strip()]
            if parts and parts[0].upper() in ("FOLDER", "DIRECTORY", "PATH"):
                continue
            if len(parts) >= 2 and parts[0]:
                result[parts[0]] = parts[1]
        return result

    def _parse_dependency_graph(self, raw: str) -> dict[str, list[str]]:
        """
        Parse the DEPENDENCY_GRAPH_PROMPT response.

        Format: COMPONENT -> DEPENDS_ON

        Args:
            raw: Raw LLM response text.

        Returns:
            dict[str, list[str]]: component → list of dependencies.
        """
        graph: dict[str, list[str]] = {}
        for line in raw.splitlines():
            line = line.strip()
            if "->" not in line:
                continue
            parts = line.split("->", 1)
            if len(parts) == 2:
                source = parts[0].strip()
                target = parts[1].strip()
                if source and target:
                    graph.setdefault(source, []).append(target)
        return graph

    # ------------------------------------------------------------------
    # Knowledge graph
    # ------------------------------------------------------------------

    @staticmethod
    def _build_knowledge_graph(understanding: RepositoryUnderstanding) -> dict:
        """
        Build a lightweight knowledge graph from parsed understanding.

        Args:
            understanding: Populated understanding object.

        Returns:
            dict: Structured graph with nodes and edges.
        """
        nodes = (
            [{"type": "module",  "name": m.name} for m in understanding.modules]
            + [{"type": "service", "name": s.name} for s in understanding.services]
            + [{"type": "api",    "name": f"{e.method} {e.route}"} for e in understanding.apis]
        )
        edges = [
            {"from": src, "to": dep}
            for src, deps in understanding.dependency_graph.items()
            for dep in deps
        ]
        return {"nodes": nodes, "edges": edges}

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    @staticmethod
    def _split_sections(text: str) -> dict[str, str]:
        """
        Split a structured LLM response into named sections.

        Sections are delimited by lines matching 'SECTION_NAME:'.

        Args:
            text: Raw LLM response text.

        Returns:
            dict[str, str]: Section name → section content.
        """
        sections: dict[str, str] = {}
        current_key: Optional[str] = None
        current_lines: list[str] = []

        for line in text.splitlines():
            stripped = line.rstrip()
            if stripped.endswith(":") and stripped[:-1].replace("_", "").isupper():
                if current_key is not None:
                    sections[current_key] = "\n".join(current_lines).strip()
                current_key = stripped[:-1]
                current_lines = []
            else:
                if current_key is not None:
                    current_lines.append(stripped)

        if current_key is not None:
            sections[current_key] = "\n".join(current_lines).strip()

        return sections

    @staticmethod
    def _scan_static_routes(repo_path: str) -> list[APIEndpoint]:
        """Scan repository files directly for Python FastAPI and Next.js App Router API routes."""
        if not repo_path or not Path(repo_path).exists():
            return []

        endpoints: list[APIEndpoint] = []
        root = Path(repo_path)

        # 1. Scan Python files for @router.post, @router.get, @app.post, @app.get
        for py_file in root.glob("**/*.py"):
            if "venv" in py_file.parts or ".venv" in py_file.parts or "node_modules" in py_file.parts:
                continue
            try:
                content = py_file.read_text(encoding="utf-8", errors="ignore")
                matches = re.findall(
                    r'@(?:router|app)\.(post|get|put|delete|patch)\(\s*["\']([^"\']+)["\']',
                    content,
                    re.IGNORECASE,
                )
                for method, route in matches:
                    purpose = f"Backend endpoint in {py_file.name}"
                    req_m = ""
                    res_m = ""

                    desc_match = re.search(r'summary=["\']([^"\']+)["\']', content)
                    if desc_match:
                        purpose = desc_match.group(1)

                    res_match = re.search(r'response_model=([A-Za-z0-9_]+)', content)
                    if res_match:
                        res_m = res_match.group(1)

                    req_match = re.search(r'def\s+\w+\s*\(\s*\w+:\s*([A-Za-z0-9_]+)', content)
                    if req_match:
                        req_m = req_match.group(1)

                    endpoints.append(APIEndpoint(
                        method=method.upper(),
                        route=route,
                        purpose=purpose,
                        request_model=req_m,
                        response_model=res_m,
                    ))
            except Exception:
                continue

        # 2. Scan Next.js API routes (src/app/api/**/route.ts or pages/api/**/*.ts)
        for route_file in root.glob("**/api/**/route.ts"):
            if "node_modules" in route_file.parts or ".next" in route_file.parts:
                continue
            try:
                rel_parts = route_file.relative_to(root).parts
                if "api" in rel_parts:
                    api_idx = rel_parts.index("api")
                    route_path = "/" + "/".join(rel_parts[api_idx:-1])
                else:
                    route_path = "/" + route_file.parent.name

                content = route_file.read_text(encoding="utf-8", errors="ignore")
                methods = re.findall(r'export\s+async\s+function\s+(GET|POST|PUT|DELETE|PATCH)', content)
                for method in set(methods):
                    endpoints.append(APIEndpoint(
                        method=method.upper(),
                        route=route_path,
                        purpose=f"Frontend API route ({route_file.parent.name})",
                        request_model="JSON",
                        response_model="JSON",
                    ))
            except Exception:
                continue

        return endpoints
