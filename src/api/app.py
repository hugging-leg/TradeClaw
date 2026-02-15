"""
FastAPI 应用

职责：
- 创建 FastAPI 实例
- 注册路由
- 配置 CORS
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from src.api.routes import (
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

    # 注册路由
    prefix = "/api"
    app.include_router(system.router, prefix=prefix, tags=["system"])
    app.include_router(portfolio.router, prefix=prefix, tags=["portfolio"])
    app.include_router(orders.router, prefix=prefix, tags=["orders"])
    app.include_router(agent.router, prefix=prefix, tags=["agent"])
    app.include_router(scheduler.router, prefix=prefix, tags=["scheduler"])
    app.include_router(settings_route.router, prefix=prefix, tags=["settings"])
    app.include_router(backtest.router, prefix=prefix, tags=["backtest"])

    return app
