"""
FastAPI 应用

职责：
- 创建 FastAPI 实例
- 注册路由
- 配置 CORS
- 配置 JWT 鉴权（当 AUTH_PASSWORD_HASH 非空时启用）
"""

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from src.api.auth import require_auth
from src.api.routes import (
    auth,
    portfolio,
    orders,
    agent,
    scheduler,
    system,
    settings as settings_route,
    backtest,
)


def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用"""
    app = FastAPI(
        title="Agent Trader API",
        description="LLM Agent Trading System API",
        version="1.0.0",
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.get_cors_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    prefix = "/api"

    # 公开路由（不需要 token）
    app.include_router(auth.router, prefix=prefix, tags=["auth"])

    # 受保护路由（鉴权启用时需要 Bearer token）
    protected = [
        (system.router, "system"),
        (portfolio.router, "portfolio"),
        (orders.router, "orders"),
        (agent.router, "agent"),
        (scheduler.router, "scheduler"),
        (settings_route.router, "settings"),
        (backtest.router, "backtest"),
    ]
    for router, tag in protected:
        app.include_router(
            router,
            prefix=prefix,
            tags=[tag],
            dependencies=[Depends(require_auth)],
        )

    return app
