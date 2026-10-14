"""/api/admin: user management, chat history review and data source status (UM-3, UM-5, UM-6, UM-8)."""
from __future__ import annotations

import threading

from fastapi import APIRouter, Depends, HTTPException

from app.api.schemas import UserUpdateRequest
from app.auth.dependencies import get_services, require_admin
from app.services import Services
from app.users.user_repository import User

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/users")
def list_users(search: str = "", admin: User = Depends(require_admin),
               services: Services = Depends(get_services)) -> list[dict]:
    users = services.users.search(search.strip())
    result = []
    for u in users:
        item = u.public()
        item["conversations"] = len(services.history.list_conversations(u.user_id, include_deleted=True))
        result.append(item)
    return result


@router.get("/users/{user_id}/conversations")
def user_conversations(user_id: int, admin: User = Depends(require_admin),
                       services: Services = Depends(get_services)) -> dict:
    target = services.users.get(user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    services.audit.record(admin_id=admin.user_id, viewed_user_id=user_id)          # UM-8
    conversations = services.history.list_conversations(user_id, include_deleted=True)
    return {"user": target.public(), "conversations": [c.public() for c in conversations]}


@router.get("/conversations/{conversation_id}")
def conversation_detail(conversation_id: int, admin: User = Depends(require_admin),
                        services: Services = Depends(get_services)) -> dict:
    conversation = services.history.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    services.audit.record(admin_id=admin.user_id, viewed_user_id=conversation.user_id,
                          conversation_id=conversation_id)                             # UM-8
    owner = services.users.get(conversation.user_id)
    messages = services.history.messages(conversation_id, include_calls=True)
    return {**conversation.public(), "owner": owner.public() if owner else None,
            "messages": [m.public(include_calls=True) for m in messages]}


@router.patch("/users/{user_id}")
def update_user(user_id: int, body: UserUpdateRequest, admin: User = Depends(require_admin),
                services: Services = Depends(get_services)) -> dict:
    target = services.users.get(user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    if target.user_id == admin.user_id and not body.is_active:
        raise HTTPException(status_code=400, detail="You cannot deactivate your own account")
    services.users.set_active(user_id, body.is_active)
    return services.users.get(user_id).public()  # type: ignore[union-attr]


@router.get("/audit")
def audit_log(admin: User = Depends(require_admin), services: Services = Depends(get_services)) -> list[dict]:
    return services.audit.recent(100)


@router.get("/sources")
def data_sources(admin: User = Depends(require_admin), services: Services = Depends(get_services)) -> list[dict]:
    result = []
    for name, agent in services.agents.items():
        result.append({
            "agent": name,
            "products": agent.repo.count(),
            "last_updated": agent.repo.last_updated(),
            "refreshing": agent._refresh_lock.locked(),
            "sites": [s.get("name") for s in agent.scraper.sites],
            "recent_runs": agent.repo.recent_runs(6),
        })
    return result


@router.post("/refresh", status_code=202)
def refresh_now(agent: str = "all", admin: User = Depends(require_admin),
                services: Services = Depends(get_services)) -> dict:
    names = list(services.agents) if agent == "all" else [agent]
    unknown = [n for n in names if n not in services.agents]
    if unknown:
        raise HTTPException(status_code=404, detail=f"Unknown agent: {', '.join(unknown)}")
    for name in names:
        threading.Thread(target=services.agents[name].refresh_data, name=f"refresh-{name}",
                         daemon=True).start()
    return {"started": names}
