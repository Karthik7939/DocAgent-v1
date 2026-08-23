"""
services/parser_service.py
---------------------------
Parses a validated GitHub push webhook payload into structured commit data.

Responsibilities:
- Extract repository metadata
- Extract branch name
- Extract HEAD commit SHA, message, timestamp, and author
- Aggregate changed files (added + modified + removed) from all commits
- Return a structured ParsedCommitData object
"""

import logging
from dataclasses import dataclass, field

from app.models.webhook import WebhookPayload

logger = logging.getLogger(__name__)


@dataclass
class ParsedCommitData:
    """Structured representation of the commit data extracted from a push payload.

    Attributes:
        repository:     Full repository name, e.g. 'owner/repo'.
        branch:         Short branch name, e.g. 'main'.
        commit_sha:     HEAD commit SHA after the push.
        commit_message: Message of the HEAD commit.
        commit_timestamp: ISO-8601 timestamp of the HEAD commit.
        author:         Name of the commit author.
        added_files:    Files added in this push.
        modified_files: Files modified in this push.
        removed_files:  Files removed in this push.
        changed_files:  Union of added + modified + removed (de-duplicated).
    """

    repository: str
    branch: str
    commit_sha: str
    commit_message: str
    commit_timestamp: str
    author: str
    added_files: list[str] = field(default_factory=list)
    modified_files: list[str] = field(default_factory=list)
    removed_files: list[str] = field(default_factory=list)
    changed_files: list[str] = field(default_factory=list)


class ParserService:
    """Converts a raw WebhookPayload into a ParsedCommitData object."""

    def parse(self, payload: WebhookPayload) -> ParsedCommitData:
        """Parse a validated push webhook payload.

        Args:
            payload: A fully validated WebhookPayload Pydantic model.

        Returns:
            ParsedCommitData: All relevant commit and repository data extracted
                              from the payload.
        """
        logger.info("Parsing commit for repository: %s", payload.repository.full_name)

        # Use the head_commit if present, otherwise fall back to the last commit.
        head = payload.head_commit or (payload.commits[-1] if payload.commits else None)

        commit_sha = head.id if head else payload.after
        commit_message = head.message if head else ""
        commit_timestamp = head.timestamp if head else ""

        logger.debug("Parsing commit SHA: %s", commit_sha)

        # Aggregate changed files across all commits in the push.
        all_added: list[str] = []
        all_modified: list[str] = []
        all_removed: list[str] = []

        for commit in payload.commits:
            all_added.extend(commit.added)
            all_modified.extend(commit.modified)
            all_removed.extend(commit.removed)

        # De-duplicate while preserving order.
        added = _deduplicate(all_added)
        modified = _deduplicate(all_modified)
        removed = _deduplicate(all_removed)

        # Union of all three lists, de-duplicated.
        changed = _deduplicate(added + modified + removed)

        logger.info(
            "Parsed %d changed file(s): added=%d  modified=%d  removed=%d",
            len(changed),
            len(added),
            len(modified),
            len(removed),
        )

        return ParsedCommitData(
            repository=payload.repository.full_name,
            branch=payload.branch,
            commit_sha=commit_sha,
            commit_message=commit_message,
            commit_timestamp=commit_timestamp,
            author=payload.pusher.name,
            added_files=added,
            modified_files=modified,
            removed_files=removed,
            changed_files=changed,
        )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _deduplicate(items: list[str]) -> list[str]:
    """Return a new list with duplicates removed, preserving insertion order.

    Args:
        items: Input list that may contain duplicate strings.

    Returns:
        list[str]: Ordered list with each string appearing at most once.
    """
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
