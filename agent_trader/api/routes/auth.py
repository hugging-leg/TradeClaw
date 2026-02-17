"""
鉴权 API — 登录 & 状态查询

公开端点（不需要 token）：
- POST /api/auth/login
- GET  /api/auth/status
"""

from fastapi import APIRouter, HTTPException, status

from config import settings
from agent_trader.api.auth import (
    LoginRequest,
    LoginResponse,
    AuthStatusResponse,
    create_access_token,
    is_auth_enabled,
    verify_password,
)

router = APIRouter()


@router.post("/auth/login", response_model=LoginResponse)
async def login(body: LoginRequest):
    """用户登录，返回 JWT token"""
    if not is_auth_enabled():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Authentication is disabled. No login required.",
        )

    if (
        body.username != settings.auth_username
        or not verify_password(body.password, settings.auth_password_hash)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    token = create_access_token(subject=body.username)
    return LoginResponse(
        access_token=token,
        expires_in=settings.jwt_expire_minutes * 60,
    )


@router.get("/auth/status", response_model=AuthStatusResponse)
async def auth_status():
    """查询鉴权是否启用（前端据此决定是否显示登录页）"""
    return AuthStatusResponse(auth_enabled=is_auth_enabled())
