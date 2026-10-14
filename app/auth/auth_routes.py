"""/api/auth: registration, login and logout (UM-1, UM-2)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response

from app.api.schemas import LoginRequest, RegisterRequest
from app.auth.dependencies import get_current_user, get_services
from app.auth.security import create_token, hash_password, verify_password
from app.services import Services
from app.users.user_repository import User

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", status_code=201)
def register(body: RegisterRequest, services: Services = Depends(get_services)) -> dict:
    if services.users.get_by_email(body.email):
        raise HTTPException(status_code=409, detail="Email already registered")
    # Public registration always creates a customer (UM-7: admins come from the setup script).
    user = services.users.create(body.name, body.email, hash_password(body.password), role="customer")
    return {"user_id": user.user_id, "name": user.name, "email": user.email, "role": user.role}


@router.post("/login")
def login(body: LoginRequest, services: Services = Depends(get_services)) -> dict:
    user = services.users.get_by_email(body.email)
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")
    services.users.touch_login(user.user_id)
    token = create_token(user.user_id, user.role, services.settings.jwt_secret, services.settings.token_hours)
    return {"token": token, "token_type": "bearer", "expires_in_hours": services.settings.token_hours,
            "user": {"user_id": user.user_id, "name": user.name, "email": user.email, "role": user.role}}


@router.post("/logout", status_code=204)
def logout(user: User = Depends(get_current_user)) -> Response:
    # Tokens are stateless; the browser discards its token.
    return Response(status_code=204)
