"""
app/api/chat.py
-----------------
Documentation chatbot API.

POST /api/chat
    Answer a question about a repository, grounded in its generated
    documentation, RAG-retrieved code context, or git history — whichever
    is relevant. See services/chat_service.py for the routing logic.

No business logic here — delegates entirely to ChatService.
"""

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.dependencies import get_chat_service
from services.chat_service import ChatMessage, ChatService

logger = logging.getLogger(__name__)

router = APIRouter()


class ChatTurn(BaseModel):
    """One prior turn in the conversation."""

    role: str = Field(..., description="'user' or 'assistant'.")
    content: str


class ChatRequest(BaseModel):
    """Request body for POST /api/chat."""

    repository_name: str = Field(..., description="Full repository name, e.g. 'owner/repo'.")
    question: str = Field(..., min_length=1, description="The user's question.")
    history: list[ChatTurn] = Field(
        default_factory=list,
        description="Prior turns in this conversation, oldest first.",
    )


class ChatResponse(BaseModel):
    """Response body for POST /api/chat."""

    answer: str
    intent: str
    sources: list[str] = Field(default_factory=list)


@router.post(
    "",
    status_code=200,
    summary="Ask a question about a repository",
    description=(
        "Answers questions grounded in the repository's generated documentation "
        "and RAG-retrieved code context. File-specific questions ('who edited X', "
        "'what's in X') are answered directly from git history / the file on disk "
        "instead of the LLM."
    ),
    response_model=ChatResponse,
)
async def chat(
    request: ChatRequest,
    chat_service: ChatService = Depends(get_chat_service),
) -> ChatResponse:
    logger.info(
        "chat request: repo=%s  question=%r",
        request.repository_name, request.question[:120],
    )

    history = [ChatMessage(role=turn.role, content=turn.content) for turn in request.history]
    result = chat_service.answer(
        repository_name=request.repository_name,
        question=request.question,
        history=history,
    )

    return ChatResponse(answer=result.answer, intent=result.intent, sources=result.sources)
