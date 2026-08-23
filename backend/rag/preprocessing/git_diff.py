"""
Git diff extraction and parsing.

This module extracts raw file changes and line-level diffs between two commits
using GitPython. It does not perform any AST or semantic analysis.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional

import git

from rag.config.constants import IGNORED_EXTENSIONS


def parse_hunks(diff_text: str) -> list[tuple[int, int]]:
    """
    Parse a unified diff text to find changed line ranges in the NEW file.

    Returns a list of (start_line, end_line) tuples.
    """
    hunks: list[tuple[int, int]] = []
    lines = diff_text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("@@"):
            match = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", line)
            if match:
                new_start = int(match.group(1))
                new_len = int(match.group(2)) if match.group(2) is not None else 1

                changed_line_numbers = set()
                current_new = new_start

                j = i + 1
                while j < len(lines) and not lines[j].startswith("@@") and not lines[j].startswith("diff --git"):
                    hunk_line = lines[j]
                    if hunk_line.startswith("+"):
                        changed_line_numbers.add(current_new)
                        current_new += 1
                    elif hunk_line.startswith("-"):
                        changed_line_numbers.add(max(1, current_new))
                    elif hunk_line.startswith("\\"):
                        pass
                    else:
                        current_new += 1
                    j += 1

                if changed_line_numbers:
                    sorted_lines = sorted(list(changed_line_numbers))
                    start = sorted_lines[0]
                    prev = sorted_lines[0]
                    for val in sorted_lines[1:]:
                        if val == prev + 1:
                            prev = val
                        else:
                            hunks.append((start, prev))
                            start = val
                            prev = val
                    hunks.append((start, prev))
                else:
                    if new_len > 0:
                        hunks.append((new_start, new_start + new_len - 1))
                    else:
                        hunks.append((new_start, new_start))
                i = j - 1
        i += 1
    return hunks


class GitDiff:
    """
    Extracts raw Git changes between two commits.
    """

    def __init__(
        self,
        repo_path: str,
        old_commit_sha: Optional[str],
        new_commit_sha: str,
    ) -> None:
        self.repo_path = repo_path
        self.old_commit_sha = old_commit_sha
        self.new_commit_sha = new_commit_sha

        self._added_files: list[str] = []
        self._modified_files: list[str] = []
        self._deleted_files: list[str] = []
        self._renamed_files: dict[str, str] = {}  # old_path -> new_path
        self._binary_files: list[str] = []
        self._changed_lines: dict[str, list[tuple[int, int]]] = {}
        self._metadata: dict[str, Any] = {}

    def extract_diff(self) -> None:
        """
        Connects to the repository and extracts the file differences.
        """
        repo = git.Repo(self.repo_path)
        new_commit = repo.commit(self.new_commit_sha)

        self._metadata = {
            "sha": new_commit.hexsha,
            "message": new_commit.message,
            "author": new_commit.author.name,
            "email": new_commit.author.email,
            "timestamp": new_commit.committed_datetime.isoformat(),
            "parents": [p.hexsha for p in new_commit.parents],
        }

        # Select target old ref to diff against
        if not self.old_commit_sha:
            if new_commit.parents:
                old_ref = new_commit.parents[0]
            else:
                old_ref = git.NULL_TREE
        else:
            try:
                old_ref = repo.commit(self.old_commit_sha)
            except Exception:
                if new_commit.parents:
                    old_ref = new_commit.parents[0]
                else:
                    old_ref = git.NULL_TREE

        if hasattr(old_ref, "hexsha") and old_ref.hexsha == new_commit.hexsha:
            return

        diffs = old_ref.diff(new_commit, create_patch=True)

        for diff in diffs:
            a_path = diff.a_path
            b_path = diff.b_path
            change_type = self._detect_change_type(diff)

            is_bin = False
            diff_text = ""
            if diff.diff:
                try:
                    diff_text = (
                        diff.diff.decode("utf-8", errors="replace")
                        if isinstance(diff.diff, bytes)
                        else str(diff.diff)
                    )
                except Exception:
                    is_bin = True

            if "Binary files" in diff_text and "differ" in diff_text:
                is_bin = True

            if not is_bin:
                for path in (a_path, b_path):
                    if path:
                        ext = Path(path).suffix.lower()
                        if ext in IGNORED_EXTENSIONS:
                            is_bin = True
                            break

            if is_bin:
                target_path = b_path if b_path else a_path
                if target_path:
                    self._binary_files.append(target_path)
                    if change_type == "A":
                        self._added_files.append(target_path)
                    elif change_type == "D":
                        self._deleted_files.append(target_path)
                    elif change_type == "R":
                        if a_path and b_path:
                            self._renamed_files[a_path] = b_path
                    else:
                        self._modified_files.append(target_path)
                continue

            # Process text files
            if change_type == "A":
                if b_path:
                    self._added_files.append(b_path)
            elif change_type == "D":
                if a_path:
                    self._deleted_files.append(a_path)
            elif change_type == "R":
                if a_path and b_path:
                    self._renamed_files[a_path] = b_path
            elif change_type == "M":
                if b_path:
                    self._modified_files.append(b_path)

            if change_type != "D" and b_path and diff_text:
                hunks = parse_hunks(diff_text)
                if hunks:
                    self._changed_lines[b_path] = hunks

    def _detect_change_type(self, diff: Any) -> str:
        """
        Returns a stable Git change type for a GitPython Diff object.

        GitPython patch diffs can leave ``change_type`` unset, so fall back to
        the boolean flags and path shape exposed by the object.
        """
        raw_change_type = getattr(diff, "change_type", None)
        if raw_change_type in {"A", "D", "R", "M"}:
            return raw_change_type

        if getattr(diff, "new_file", False):
            return "A"
        if getattr(diff, "deleted_file", False):
            return "D"
        if getattr(diff, "renamed_file", False):
            return "R"

        a_path = getattr(diff, "a_path", None)
        b_path = getattr(diff, "b_path", None)
        if not a_path and b_path:
            return "A"
        if a_path and not b_path:
            return "D"
        if a_path and b_path and a_path != b_path:
            return "R"
        return "M"

    def changed_files(self) -> list[str]:
        """
        Returns all files added, modified, or renamed.
        """
        result = []
        result.extend(self._added_files)
        result.extend(self._modified_files)
        result.extend(self._renamed_files.values())
        return list(dict.fromkeys(result))

    def added_files(self) -> list[str]:
        """
        Returns files added.
        """
        return self._added_files

    def modified_files(self) -> list[str]:
        """
        Returns files modified.
        """
        return self._modified_files

    def deleted_files(self) -> list[str]:
        """
        Returns files deleted.
        """
        return self._deleted_files

    def renamed_files(self) -> dict[str, str]:
        """
        Returns mapping of old_path -> new_path.
        """
        return self._renamed_files

    def changed_lines(self) -> dict[str, list[tuple[int, int]]]:
        """
        Returns mapping of file_path -> list of (start_line, end_line) tuples.
        """
        return self._changed_lines

    def commit_metadata(self) -> dict[str, Any]:
        """
        Returns commit metadata dict.
        """
        return self._metadata

    def binary_files(self) -> list[str]:
        """
        Returns binary files detected.
        """
        return self._binary_files
