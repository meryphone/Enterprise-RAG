"""Auth endpoints: POST /auth/login and GET /auth/me."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.auth.dependencies import create_token, require_auth
from app.auth.models import get_user_by_email, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str
    password: str
    remember: bool = False


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest) -> TokenResponse:
    user = get_user_by_email(req.email)
    if user is None or not verify_password(req.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales incorrectas.",
        )
    token = create_token(email=user["email"], role=user["role"], remember=req.remember)
    return TokenResponse(access_token=token)


@router.get("/me")
def me(current_user: dict = Depends(require_auth)) -> dict:
    user = get_user_by_email(current_user["email"])
    return {
        "email": user["email"],
        "full_name": user["full_name"],
        "role": user["role"],
    }
