"""/api/chat and /api/me."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.schemas import ChatRequest
from app.auth.dependencies import get_current_user, get_services
from app.services import Services
from app.users.user_repository import User

router = APIRouter(prefix="/api", tags=["chat"])


@router.get("/me")
def me(user: User = Depends(get_current_user)) -> dict:
    return {"user_id": user.user_id, "name": user.name, "email": user.email, "role": user.role}


@router.post("/chat")
async def chat(body: ChatRequest, user: User = Depends(get_current_user),
               services: Services = Depends(get_services)) -> dict:
    if body.conversation_id is None:
        conversation = services.history.create_conversation(user.user_id, body.message)
    else:
        conversation = services.history.get_conversation(body.conversation_id)
        if conversation is None or conversation.is_deleted:
            raise HTTPException(status_code=404, detail="Conversation not found")
        if conversation.user_id != user.user_id:
            raise HTTPException(status_code=403, detail="Not your conversation")
    result = await services.central.handle(user.user_id, conversation.conversation_id, body.message)
    return {"conversation_id": conversation.conversation_id, "title": conversation.title,
            "reply": result.reply, "categories": result.categories, "message_id": result.message_id,
            "intro": result.meta.get("intro"), "sections": result.meta.get("sections"),
            "budget": result.meta.get("budget"), "footer": result.meta.get("footer"),
            "trace": result.trace}
