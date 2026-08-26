"""
tests/test_chat_service.py
----------------------------
Unit tests for ChatService.

Tests:
- Intent classification for file-history, file-content, and general questions
- File resolution: exact path, basename match, multiple matches, no match
- answer() routes to the git-history handler without calling the LLM
- answer() routes to the file-content handler without calling the LLM
- answer() falls back to the LLM-backed general handler
- General handler degrades gracefully when RAG retrieval is unavailable
"""

from unittest.mock import MagicMock

import pytest

from services.chat_service import ChatService


@pytest.fixture()
def repo_dir(tmp_path):
    """A small fake repository with one nested source file."""
    (tmp_path / "app" / "api").mkdir(parents=True)
    (tmp_path / "app" / "api" / "webhook.py").write_text(
        "def handle_webhook():\n    return 'ok'\n", encoding="utf-8"
    )
    return tmp_path


@pytest.fixture()
def chat_service(repo_dir) -> ChatService:
    fake_repo_service = MagicMock()
    fake_repo_service.get_repository_path.return_value = str(repo_dir)

    fake_git_service = MagicMock()
    fake_git_service.get_file_history.return_value = [
        {
            "sha": "abc12345",
            "author": "Alice",
            "email": "alice@example.com",
            "date": "2026-08-25T11:34:30+05:30",
            "message": "Add webhook handler",
        }
    ]

    fake_llm = MagicMock()
    fake_llm.generate.return_value = "The webhook receives GitHub push events."

    return ChatService(
        repository_service=fake_repo_service,
        git_service=fake_git_service,
        llm_client=fake_llm,
    )


# ---------------------------------------------------------------------------
# Intent classification
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("question", [
    "Who edited webhook.py?",
    "who changed app/api/webhook.py last",
    "What's the commit history of webhook.py",
    "when was webhook.py last modified",
])
def test_classify_file_history(question: str) -> None:
    intent, hint = ChatService._classify(question)
    assert intent == "file_history"
    assert hint and "webhook.py" in hint


@pytest.mark.parametrize("question", [
    "What's in webhook.py?",
    "show me webhook.py",
    "contents of webhook.py",
])
def test_classify_file_content(question: str) -> None:
    intent, hint = ChatService._classify(question)
    assert intent == "file_content"
    assert hint and "webhook.py" in hint


def test_classify_general_for_conceptual_question() -> None:
    intent, hint = ChatService._classify("What does this project do?")
    assert intent == "general"


# ---------------------------------------------------------------------------
# File resolution
# ---------------------------------------------------------------------------

def test_resolve_file_exact_path(repo_dir) -> None:
    matches = ChatService._resolve_file(str(repo_dir), "app/api/webhook.py")
    assert matches == ["app/api/webhook.py"]


def test_resolve_file_basename_match(repo_dir) -> None:
    matches = ChatService._resolve_file(str(repo_dir), "webhook.py")
    assert matches == ["app/api/webhook.py"]


def test_resolve_file_multiple_matches(repo_dir) -> None:
    (repo_dir / "lib").mkdir()
    (repo_dir / "lib" / "webhook.py").write_text("# duplicate name\n", encoding="utf-8")
    matches = ChatService._resolve_file(str(repo_dir), "webhook.py")
    assert sorted(matches) == sorted(["app/api/webhook.py", "lib/webhook.py"])


def test_resolve_file_no_match(repo_dir) -> None:
    matches = ChatService._resolve_file(str(repo_dir), "nonexistent.py")
    assert matches == []


# ---------------------------------------------------------------------------
# answer() routing
# ---------------------------------------------------------------------------

def test_answer_routes_to_file_history(chat_service: ChatService) -> None:
    result = chat_service.answer("owner/demo", "who edited webhook.py?")
    assert result.intent == "file_history"
    assert "Alice" in result.answer
    assert result.sources == ["app/api/webhook.py"]
    chat_service._llm.generate.assert_not_called()


def test_answer_routes_to_file_content(chat_service: ChatService) -> None:
    result = chat_service.answer("owner/demo", "what is in webhook.py")
    assert result.intent == "file_content"
    assert "handle_webhook" in result.answer
    chat_service._llm.generate.assert_not_called()


def test_answer_falls_back_to_general(chat_service: ChatService) -> None:
    result = chat_service.answer("owner/demo", "what does this project do?")
    assert result.intent == "general"
    chat_service._llm.generate.assert_called_once()


def test_general_handler_survives_rag_failure(chat_service: ChatService, monkeypatch) -> None:
    """Repo not indexed (RetrievalPipeline unavailable) should not crash the answer."""
    monkeypatch.setattr(ChatService, "_retrieve_code_context", lambda self, repo, q: "")
    result = chat_service.answer("owner/demo", "what does this project do?")
    assert result.intent == "general"
    assert result.answer
