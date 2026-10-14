"""FastAPI dependencies for authentication and role checks (UM-3, UM-4)."""
from __future__ import annotations

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth.security import decode_token
from app.services import Services
from app.users.user_repository import User

bearer = HTTPBearer(auto_error=False)


def get_services(request: Request) -> Services:
    return request.app.state.services


def get_current_user(cred: HTTPAuthorizationCredentials | None = Depends(bearer),
                     services: Services = Depends(get_services)) -> User:
    if cred is None or not cred.credentials:
        raise HTTPException(status_code=401, detail="Login required")
    try:
        payload = decode_token(cred.credentials, services.settings.jwt_secret)
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Session expired, please log in again")
    user = services.users.get(user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Account not found")
    if not user.is_active:
        raise HTTPException(status_code=401, detail="Account disabled")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admins only")
    return user
