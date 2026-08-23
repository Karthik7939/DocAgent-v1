"""
Incremental pipeline module.

Triggers incremental indexing and query building on git commits.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import git

from rag.indexing.incremental import IncrementalIndexer
from rag.parsing.language_detector import LanguageDetector
from rag.parsing.symbol_extractor import SymbolExtractor
from rag.preprocessing.ast_diff import ASTDiff
from rag.preprocessing.git_diff import GitDiff
from rag.preprocessing.query_builder import QueryBuilder
from rag.preprocessing.semantic_change import SemanticChange
from rag.retrieval.keyword_store import KeywordStore
from rag.retrieval.vector_store_factory import get_vector_store
from rag.schemas.change import SymbolChange, SymbolType
from rag.schemas.query import SemanticQuery
from rag.utils import get_logger
from rag.utils.file_loader import load_text_file

logger = get_logger(__name__)


class IncrementalPipeline:
    """
    Orchestrates processing incremental changes for a commit.
    """

    def __init__(
        self,
        repository_path: str,
        repository_name: str,
        old_commit_sha: Optional[str],
        new_commit_sha: str,
        vector_store=None,
        keyword_store: Optional[KeywordStore] = None,
    ) -> None:
        self.repository_path = Path(repository_path)
        self.repository_name = repository_name
        self.old_commit_sha = old_commit_sha
        self.new_commit_sha = new_commit_sha

        self.vector_store = vector_store or get_vector_store(repository=repository_name)
        self.keyword_store = keyword_store or KeywordStore(repository=repository_name)

    def run(self, workflow_id: Optional[str] = None) -> SemanticQuery:
        """
        Orchestrates pipeline execution.
        """
        return self.process_commit(workflow_id=workflow_id)

    def _file_diff(self, repo: git.Repo, file_path: str) -> str:
        """Return a file's commit diff, falling back to an empty string."""
        try:
            if self.old_commit_sha:
                return repo.git.diff(
                    self.old_commit_sha,
                    self.new_commit_sha,
                    "--",
                    file_path,
                )
            return repo.git.show(self.new_commit_sha, "--", file_path)
        except Exception as e:
            logger.debug("Failed to extract git diff string for %s: %s", file_path, e)
            return ""

    def process_commit(self, workflow_id: Optional[str] = None) -> SemanticQuery:
        """
        Executes Git Diff, AST Diff, Semantic Classification, and updates indexes.
        """
        logger.info(
            "Processing commit incrementally: %s -> %s",
            self.old_commit_sha,
            self.new_commit_sha,
        )

        try:
            if workflow_id:
                from rag.pipeline.events import PipelineStarted
                from rag.pipeline.manager import handle_event
                try:
                    handle_event(PipelineStarted(workflow_id, self.repository_name, self.new_commit_sha))
                except Exception:
                    pass

            # 1. Git Diff extraction
            git_diff = GitDiff(
                repo_path=str(self.repository_path),
                old_commit_sha=self.old_commit_sha or "",
                new_commit_sha=self.new_commit_sha,
            )
            git_diff.extract_diff()

            added_files = git_diff.added_files()
            modified_files = git_diff.modified_files()
            deleted_files = git_diff.deleted_files()
            renamed_files = git_diff.renamed_files()

            # Retrieve git repository details
            repo = git.Repo(self.repository_path)

            added_symbols: list[SymbolChange] = []
            modified_symbols: list[SymbolChange] = []
            removed_symbols: list[SymbolChange] = []
            imports_added: list[str] = []
            imports_removed: list[str] = []
            diff_texts: list[str] = []
            implementation_terms: list[str] = []
            calls: list[str] = []
            structural_operations: list[str] = []
            data_flows: list[str] = []
            renamed_symbols: list[dict[str, str]] = []
            ast_profiles: dict[str, dict[str, bool]] = {}
            file_contexts: list[dict[str, Any]] = []

            # 2. AST Diff comparison
            for f in modified_files:
                lang = LanguageDetector.detect(f)
                if lang in ("unknown", "documentation"):
                    continue

                file_diff = self._file_diff(repo, f)

                # Load new file content
                new_content = ""
                try:
                    new_content = load_text_file(self.repository_path / f)
                except Exception as e:
                    logger.warning("Could not read modified file %s: %s", f, e)
                    continue

                # Load old file content from git tree
                old_content = ""
                if self.old_commit_sha:
                    try:
                        old_commit = repo.commit(self.old_commit_sha)
                        old_content = (
                            (old_commit.tree / f)
                            .data_stream.read()
                            .decode("utf-8", errors="replace")
                        )
                    except Exception as e:
                        logger.debug("Failed to read old commit content for %s: %s", f, e)

                ast_diff = ASTDiff(old_content, new_content, lang)
                ast_diff.compare()

                file_added_symbols = ast_diff.added_symbols()
                file_modified_symbols = ast_diff.modified_symbols()
                file_removed_symbols = ast_diff.deleted_symbols()
                file_imports_added = ast_diff.imports_added()
                file_imports_removed = ast_diff.imports_removed()
                file_calls = ast_diff.calls_added()
                file_operations = ast_diff.operations_added()
                file_data_flows = ast_diff.data_flows_added()

                added_symbols.extend(file_added_symbols)
                modified_symbols.extend(file_modified_symbols)
                removed_symbols.extend(file_removed_symbols)
                imports_added.extend(file_imports_added)
                imports_removed.extend(file_imports_removed)
                implementation_terms.extend(file_calls)
                implementation_terms.extend(file_operations)
                calls.extend(file_calls)
                structural_operations.extend(file_operations)
                data_flows.extend(file_data_flows)
                renamed_symbols.extend(ast_diff.renamed_symbols())
                ast_profiles[f] = ast_diff.structural_profile()
                file_contexts.append(
                    {
                        "file_path": f,
                        "language": lang,
                        "change_type": "modified",
                        "symbols": [symbol.name for symbol in file_added_symbols + file_modified_symbols + file_removed_symbols],
                        "imports_added": file_imports_added,
                        "imports_removed": file_imports_removed,
                        "calls": file_calls,
                        "operations": file_operations,
                        "data_flows": file_data_flows,
                        "diff_text": file_diff,
                        "semantic_change": "logic",
                    }
                )

            # For added files, extract symbols
            extractor = SymbolExtractor()
            for f in added_files:
                lang = LanguageDetector.detect(f)
                if lang in ("unknown", "documentation"):
                    continue
                try:
                    content = load_text_file(self.repository_path / f)
                    res = extractor.extract(content, lang)
                    file_symbols: list[str] = []
                    for sym in res.all_symbols:
                        try:
                            symbol_type = SymbolType(sym.symbol_type)
                        except ValueError:
                            symbol_type = SymbolType.UNKNOWN
                        added_symbols.append(
                            SymbolChange(
                                name=sym.name,
                                symbol_type=symbol_type,
                                start_line=sym.start_line,
                                end_line=sym.end_line,
                            )
                        )
                        file_symbols.append(sym.name)
                    imports_added.extend(res.imports)
                    implementation_terms.extend(res.calls)
                    implementation_terms.extend(res.operations)
                    calls.extend(res.calls)
                    structural_operations.extend(res.operations)
                    data_flows.extend(res.data_flows)
                    file_contexts.append(
                        {
                            "file_path": f,
                            "language": lang,
                            "change_type": "added",
                            "symbols": file_symbols,
                            "imports_added": res.imports,
                            "imports_removed": [],
                            "calls": res.calls,
                            "operations": res.operations,
                            "data_flows": res.data_flows,
                            "diff_text": "",
                            "semantic_change": "logic",
                        }
                    )
                except Exception as e:
                    logger.warning("Could not parse added file %s: %s", f, e)

            # 3. Semantic Change classification
            change_types: list[str] = []
            for f in modified_files + added_files + list(renamed_files.values()):
                lang = LanguageDetector.detect(f)
                if lang in ("unknown", "documentation"):
                    continue

                file_diff = self._file_diff(repo, f)

                if file_diff:
                    diff_texts.append(file_diff)

                sem_change = SemanticChange(
                    file_path=f,
                    change_type_git=(
                        "modified"
                        if f in modified_files
                        else ("added" if f in added_files else "renamed")
                    ),
                    added_symbols=added_symbols if f in added_files else [],
                    modified_symbols=modified_symbols if f in modified_files else [],
                    removed_symbols=removed_symbols if f in deleted_files else [],
                    imports_added=imports_added,
                    imports_removed=imports_removed,
                    diff_text=file_diff,
                    language=lang,
                    ast_profile=ast_profiles.get(f),
                    renamed_symbols=renamed_symbols,
                )
                sem_change.classify()
                change_types.append(sem_change.change_type())

                if f not in {context["file_path"] for context in file_contexts}:
                    file_contexts.append(
                        {
                            "file_path": f,
                            "language": lang,
                            "change_type": "renamed" if f in renamed_files.values() else "modified",
                            "symbols": [symbol.name for symbol in added_symbols + modified_symbols + removed_symbols],
                            "imports_added": imports_added,
                            "imports_removed": imports_removed,
                            "calls": calls,
                            "operations": structural_operations,
                            "data_flows": data_flows,
                            "diff_text": file_diff,
                            "semantic_change": sem_change.change_type(),
                        }
                    )

            # Determine overall change classification
            priority = [
                "documentation",
                "formatting",
                "comment",
                "rename",
                "configuration",
                "api",
                "refactor",
                "logic",
            ]
            overall_change_type = next(
                (change_type for change_type in priority if change_type in change_types),
                "logic",
            )

            # 4. Dependency graph loading & Query Builder
            from rag.parsing.dependency_graph import DependencyGraphQuery, GraphPersistence

            persistence = GraphPersistence()
            graph_query = None
            if persistence.graph_path.exists():
                try:
                    graph = persistence.load()
                    graph_query = DependencyGraphQuery(graph)
                except Exception as e:
                    logger.warning("Could not load dependency graph: %s", e)

            query_builder = QueryBuilder(
                self.repository_name,
                self.new_commit_sha,
                graph_query,
            )
            query = query_builder.build(
                changed_files=git_diff.changed_files(),
                changed_symbols=added_symbols + modified_symbols + removed_symbols,
                change_type=overall_change_type,
                imports_added=imports_added,
                imports_removed=imports_removed,
                diff_texts=diff_texts,
                implementation_terms=implementation_terms,
                calls=calls,
                structural_operations=structural_operations,
                data_flows=data_flows,
                renamed_symbols=renamed_symbols,
                file_contexts=file_contexts,
            )

            if workflow_id:
                from rag.pipeline.manager import get_workflow_manager

                state = get_workflow_manager().load_workflow(workflow_id)
                if state:
                    state.semantic_query = query.model_dump(mode="json")
                    state.ast_details = [
                        {
                            "file_path": context["file_path"],
                            "language": context["language"],
                            "change_type": context["change_type"],
                            "symbols": context["symbols"],
                            "imports_added": context["imports_added"],
                            "imports_removed": context["imports_removed"],
                            "operations": context["operations"],
                            "data_flows": context["data_flows"],
                            "structural_profile": ast_profiles.get(context["file_path"], {}),
                        }
                        for context in file_contexts
                    ]
                    get_workflow_manager().save_workflow(state)

            # 5. Incremental index update
            if workflow_id:
                self.update_repository(
                    added_files,
                    modified_files,
                    deleted_files,
                    renamed_files,
                    workflow_id=workflow_id,
                )
            else:
                self.update_repository(
                    added_files,
                    modified_files,
                    deleted_files,
                    renamed_files,
                )

            if workflow_id:
                from rag.pipeline.events import PipelineCompleted
                from rag.pipeline.manager import handle_event
                try:
                    handle_event(PipelineCompleted(workflow_id, 0.0))
                except Exception:
                    pass

            return query

        except Exception as e:
            if workflow_id:
                from rag.pipeline.events import PipelineFailed
                from rag.pipeline.manager import handle_event
                try:
                    handle_event(PipelineFailed(workflow_id, str(e)))
                except Exception:
                    pass
            raise e

    def update_repository(
        self,
        added_files: list[str],
        modified_files: list[str],
        deleted_files: list[str],
        renamed_files: dict[str, str],
        workflow_id: Optional[str] = None,
    ) -> None:
        """
        Runs incremental updates against FAISS, BM25, and dependency graph.
        """
        indexer = IncrementalIndexer(
            repository_path=str(self.repository_path),
            repository_name=self.repository_name,
            commit_sha=self.new_commit_sha,
            vector_store=self.vector_store,
            keyword_store=self.keyword_store,
        )
        if workflow_id:
            indexer.update(
                added_files=added_files,
                modified_files=modified_files,
                deleted_files=deleted_files,
                renamed_files=renamed_files,
                workflow_id=workflow_id,
            )
        else:
            indexer.update(
                added_files=added_files,
                modified_files=modified_files,
                deleted_files=deleted_files,
                renamed_files=renamed_files,
            )
        indexer.sync()
