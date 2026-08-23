"""
agents/sync/sync_agent.py
--------------------------
Sync Agent — persists generated per-file documentation to the filesystem.

Responsibilities:
- Read all per-file documents from SharedMemory.documentation.file_docs.
- Create the output directory structure mirroring the source tree.
- Write each Markdown file to disk (overwriting if it already exists).
- Verify files were written correctly.
- Produce a synchronisation report.
- Write the sync report into SharedMemory.workflow.

This agent MUST NOT:
- Generate documentation.
- Validate documentation.
- Revise documentation.
- Read repository source code.
- Call the LLM.
- Query the RAG pipeline.
"""

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

from agents.coordinator.coordinator import AgentResult
from agents.memory.shared_memory import SharedMemory

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Sync report
# ---------------------------------------------------------------------------

@dataclass
class SyncReport:
    """Summary of the sync operation.

    Attributes:
        documents_written:  Number of files successfully written.
        documents_skipped:  Number of files skipped (e.g. empty content).
        documents_updated:  Number of files that overwrote existing files.
        total_size_bytes:   Combined size of all written files.
        output_directory:   Root output directory path.
        execution_time:     Duration of the sync operation in seconds.
        written_files:      Absolute paths of successfully written files.
        errors:             Any errors encountered during writing.
    """

    documents_written: int = 0
    documents_skipped: int = 0
    documents_updated: int = 0
    total_size_bytes: int = 0
    output_directory: str = ""
    execution_time: float = 0.0
    written_files: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialise the sync report."""
        return {
            "documents_written": self.documents_written,
            "documents_skipped": self.documents_skipped,
            "documents_updated": self.documents_updated,
            "total_size_bytes": self.total_size_bytes,
            "output_directory": self.output_directory,
            "execution_time": self.execution_time,
            "written_files": self.written_files,
            "errors": self.errors,
        }


# ---------------------------------------------------------------------------
# Sync Agent
# ---------------------------------------------------------------------------

class SyncAgent:
    """
    Writes generated per-file Markdown documentation to the filesystem.

    Each source file's documentation is saved as:
        <output_dir>/<repo-slug>/<original/file/path>.md

    This mirrors the source tree structure so every documented file has a
    corresponding Markdown file in the output directory.

    This is the only agent that writes files to disk.

    Args:
        output_dir:  Root directory for generated documentation.
                     Defaults to 'generated_docs'.
        overwrite:   If True, overwrite existing files (enables update behaviour).
                     If False, skip files that already exist.
    """

    def __init__(
        self,
        output_dir: str = "generated_docs",
        overwrite: bool = True,
    ) -> None:
        self._output_dir = Path(output_dir)
        self._overwrite = overwrite

    def run(self, shared_memory: SharedMemory) -> AgentResult:
        """
        Persist all per-file documents to disk.

        Reads:  shared_memory.documentation.file_docs
        Writes: filesystem under self._output_dir / <repo-slug> /
                shared_memory.workflow (sync duration stored in execution_times)

        Args:
            shared_memory: The shared memory object.

        Returns:
            AgentResult: Success or failure result for the Coordinator.
        """
        start = time.monotonic()
        repo_name = shared_memory.repository.full_name or shared_memory.repository.name
        logger.info("Sync started: %s", repo_name)

        file_docs = shared_memory.documentation.all_documents()

        if not file_docs:
            return AgentResult(
                success=False,
                message="No file docs to sync — documentation section is empty",
                recoverable=False,
            )

        # Build repository-specific output dir: generated_docs/owner_repo/
        repo_slug = repo_name.replace("/", "_")
        repo_output_dir = self._output_dir / repo_slug

        report = SyncReport(output_directory=str(repo_output_dir))

        self._ensure_directory(repo_output_dir)
        logger.info("Output directory verified: %s", repo_output_dir)

        # Write per-file documents
        logger.info("Writing per-file docs: %d file(s)", len(file_docs))
        for src_path, content in file_docs.items():
            if not content or not content.strip():
                report.documents_skipped += 1
                continue

            out_path = self._file_doc_path(repo_output_dir, src_path)
            self._ensure_directory(out_path.parent)

            result = self._write_file(out_path, content)
            if result["success"]:
                if result["updated"]:
                    report.documents_updated += 1
                report.documents_written += 1
                report.total_size_bytes += result["size"]
                report.written_files.append(str(out_path))
                logger.info("File doc saved [%s]: %s", "updated" if result["updated"] else "new", out_path)
            else:
                report.errors.append(result["error"])
                logger.error("Failed to write file doc %s: %s", out_path, result["error"])

        duration = time.monotonic() - start
        report.execution_time = duration

        logger.info(
            "Sync completed: written=%d  skipped=%d  updated=%d  size=%d bytes",
            report.documents_written,
            report.documents_skipped,
            report.documents_updated,
            report.total_size_bytes,
        )

        # Store sync duration in workflow metadata
        shared_memory.workflow.execution_times["sync"] = duration

        if report.errors:
            return AgentResult(
                success=False,
                message=f"Sync completed with {len(report.errors)} error(s)",
                execution_time=duration,
                errors=report.errors,
                recoverable=True,
            )

        return AgentResult(
            success=True,
            message=(
                f"Sync completed: {report.documents_written} written, "
                f"{report.documents_skipped} skipped, "
                f"{report.total_size_bytes} bytes"
            ),
            execution_time=duration,
        )

    # ------------------------------------------------------------------
    # File system helpers
    # ------------------------------------------------------------------

    def _write_file(self, file_path: Path, content: str) -> dict:
        """Write content to a file.

        Before overwriting an existing file, saves the current content to a
        ``.prev.md`` sidecar so the documents API can return the previous
        version for diff/change-highlighting in the review frontend.

        Args:
            file_path: Absolute path to write to.
            content:   Markdown string to write.

        Returns:
            dict: {success, updated, size, error}
        """
        updated = file_path.exists()

        if updated and not self._overwrite:
            return {"success": False, "updated": False, "size": 0,
                    "error": f"Skipped (overwrite=False): {file_path}"}

        try:
            # Save the previous version as a sidecar before overwriting.
            # The documents API reads this to populate `previousContent`
            # for the frontend diff viewer.
            if updated:
                prev_path = file_path.with_suffix(".prev.md")
                try:
                    prev_path.write_text(
                        file_path.read_text(encoding="utf-8"), encoding="utf-8"
                    )
                    logger.debug("Previous content saved to sidecar: %s", prev_path)
                except OSError as sidecar_exc:
                    # Sidecar write failure is non-fatal — log and continue.
                    logger.warning(
                        "Could not write .prev.md sidecar for %s: %s",
                        file_path, sidecar_exc,
                    )

            file_path.write_text(content, encoding="utf-8")
            size = file_path.stat().st_size
            return {"success": True, "updated": updated, "size": size, "error": ""}
        except OSError as exc:
            return {"success": False, "updated": False, "size": 0,
                    "error": f"Write failed: {file_path}: {exc}"}

    @staticmethod
    def _ensure_directory(directory: Path) -> None:
        """Create a directory and all parents if they do not exist.

        Args:
            directory: Path to create.

        Raises:
            RuntimeError: If the directory cannot be created.
        """
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise RuntimeError(f"Cannot create output directory {directory}: {exc}") from exc

    @staticmethod
    def _file_doc_path(repo_output_dir: Path, src_path: str) -> Path:
        """Convert a source-file relative path to its documentation output path.

        The output mirrors the source directory structure under the repo output
        directory, with a ``.md`` extension appended.

        Examples::

            src_path = "app/api/webhook.py"
            → repo_output_dir / "app" / "api" / "webhook.py.md"

        Args:
            repo_output_dir: Root output directory for this repository.
            src_path:        Relative path of the source file (uses forward or
                             back slashes).

        Returns:
            Path: Absolute path for the Markdown output file.
        """
        # Normalise separators so both / and \ work on any OS
        normalised = src_path.replace("\\", "/")
        if not normalised.endswith(".md"):
            return repo_output_dir / normalised / f"{normalised}.md"
        return repo_output_dir / normalised
