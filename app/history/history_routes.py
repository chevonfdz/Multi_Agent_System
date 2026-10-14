"""/api/conversations: a customer's own chat history (FR-1)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response

from app.auth.dependencies import get_current_user, get_services
from app.history.history_repository import Conversation
from app.services import Services
from app.users.user_repository import User

router = APIRouter(prefix="/api/conversations", tags=["history"])


def _owned(conversation_id: int, user: User, services: Services) -> Conversation:
    conversation = services.history.get_conversation(conversation_id)
    if conversation is None or conversation.is_deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if conversation.user_id != user.user_id:                  # UM-4: owners only
        raise HTTPException(status_code=403, detail="Not your conversation")
    return conversation


@router.get("")
def list_conversations(user: User = Depends(get_current_user),
                       services: Services = Depends(get_services)) -> list[dict]:
    return [c.public() for c in services.history.list_conversations(user.user_id)]


@router.get("/{conversation_id}")
def get_conversation(conversation_id: int, user: User = Depends(get_current_user),
                     services: Services = Depends(get_services)) -> dict:
    conversation = _owned(conversation_id, user, services)
    messages = services.history.messages(conversation_id)
    return {**conversation.public(), "messages": [m.public() for m in messages]}


@router.delete("/{conversation_id}", status_code=204)
def delete_conversation(conversation_id: int, user: User = Depends(get_current_user),
                        services: Services = Depends(get_services)) -> Response:
    _owned(conversation_id, user, services)
    services.history.soft_delete(conversation_id)
    return Response(status_code=204)
