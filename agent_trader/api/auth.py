"""
JWT 鉴权模块

- 当 AUTH_PASSWORD_HASH 为空时，鉴权关闭（开发模式）
- 当 AUTH_PASSWORD_HASH 已设置时，所有 API 请求（除 /api/auth/*）需要 Bearer token
- /api/auth/login 接受 username + password，返回 JWT access_token
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel

from config import settings

# ========== Password hashing ==========


def hash_password(plain: str) -> str:
    """生成 bcrypt 哈希"""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """验证密码"""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


# ========== JWT ==========


def create_access_token(
    subject: str,
    expires_delta: Optional[timedelta] = None,
) -> str:
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.jwt_expire_minutes)
    )
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> str:
    """解码 token，返回 subject（用户名）。无效则抛异常。"""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        sub: Optional[str] = payload.get("sub")
        if sub is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
            )
        return sub
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired or invalid",
        )


# ========== Auth state ==========


def is_auth_enabled() -> bool:
    """鉴权是否启用（AUTH_PASSWORD_HASH 非空即启用）"""
    return bool(settings.auth_password_hash and settings.auth_password_hash.strip())


# ========== FastAPI dependency ==========

_bearer_scheme = HTTPBearer(auto_error=False)


async def require_auth(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> Optional[str]:
    """
    FastAPI 依赖：
    - 鉴权关闭时直接放行，返回 None
    - 鉴权开启时验证 Bearer token，返回用户名
    """
    if not is_auth_enabled():
        return None

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return decode_access_token(credentials.credentials)


# ========== Request / Response models ==========


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class AuthStatusResponse(BaseModel):
    auth_enabled: bool
    username: Optional[str] = None
