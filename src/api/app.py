"""
FastAPI 应用

职责：
- 创建 FastAPI 实例
- 注册路由
- 配置 CORS
- 配置 JWT 鉴权（当 AUTH_PASSWORD_HASH 非空时启用）
- Serve 前端 SPA 静态文件（生产部署时）
"""

from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

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

# 前端构建产物目录
_FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"


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

    # ---------- Serve frontend SPA ----------
    # 仅当 frontend/dist 存在时挂载（开发时前端单独启动，不需要此功能）
    if _FRONTEND_DIR.is_dir():
        # 静态资源 (JS/CSS/images) — Vite 构建产物在 assets/ 下
        app.mount(
            "/assets",
            StaticFiles(directory=_FRONTEND_DIR / "assets"),
            name="frontend-assets",
        )

        # SPA fallback: 所有非 /api 路由返回 index.html，由前端路由处理
        @app.get("/{full_path:path}")
        async def serve_spa(full_path: str):
            # 尝试返回对应的静态文件（如 favicon.ico, robots.txt 等）
            file_path = _FRONTEND_DIR / full_path
            if full_path and file_path.is_file():
                return FileResponse(file_path)
            # 其他路由一律返回 index.html（SPA client-side routing）
            return FileResponse(_FRONTEND_DIR / "index.html")

    return app
