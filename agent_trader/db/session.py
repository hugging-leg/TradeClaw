"""
数据库会话管理

使用 SQLAlchemy 2.0 异步模式
"""

from agent_trader.utils.logging_config import get_logger
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
    async_sessionmaker
)
from sqlalchemy.pool import NullPool

from config import settings
from .models import Base

logger = get_logger(__name__)

# 全局引擎和会话工厂
_engine = None
_session_factory = None


def _get_async_database_url() -> str:
    """
    转换数据库 URL 为异步驱动格式。

    get_database_url() 已经标准化了 PostgreSQL dialect：
      - SQLite:     sqlite:///...          -> sqlite+aiosqlite:///...
      - PostgreSQL: postgresql+psycopg://.. -> postgresql+psycopg_async://..
    """
    url = settings.get_database_url()

    if url.startswith('sqlite'):
        # sqlite:///... -> sqlite+aiosqlite:///...
        return url.replace('sqlite:', 'sqlite+aiosqlite:', 1)
    elif 'postgresql' in url or 'postgres' in url:
        # postgresql+psycopg://... -> postgresql+psycopg_async://...
        return url.replace('+psycopg://', '+psycopg_async://', 1)

    return url


async def init_db():
    """初始化数据库连接和表"""
    global _engine, _session_factory

    if _engine is not None:
        return

    try:
        db_url = _get_async_database_url()
        logger.info(f"初始化数据库: {db_url.split('@')[-1] if '@' in db_url else db_url}")

        is_sqlite = 'sqlite' in db_url

        # 创建异步引擎
        _engine = create_async_engine(
            db_url,
            echo=False,
            poolclass=NullPool if is_sqlite else None,
        )

        # SQLite: 启用 WAL 模式以允许并发读写，减少 "database is locked" 错误
        if is_sqlite:
            from sqlalchemy import event, text

            @event.listens_for(_engine.sync_engine, "connect")
            def _set_sqlite_pragma(dbapi_conn, connection_record):
                cursor = dbapi_conn.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA busy_timeout=5000")
                cursor.close()

        # 创建会话工厂
        _session_factory = async_sessionmaker(
            bind=_engine,
            class_=AsyncSession,
            expire_on_commit=False
        )

        # 创建表（如果不存在）
        async with _engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        logger.info("数据库初始化完成")

    except Exception as e:
        logger.error(f"数据库初始化失败: {e}")
        raise


async def close_db():
    """关闭数据库连接"""
    global _engine, _session_factory

    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
        logger.info("数据库连接已关闭")


@asynccontextmanager
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    获取数据库会话（上下文管理器）

    用法:
        async with get_db() as db:
            result = await db.execute(query)
    """
    if _session_factory is None:
        await init_db()

    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


class DatabaseSession:
    """
    数据库会话助手类

    用于需要手动管理会话生命周期的场景
    """

    def __init__(self):
        self._session: Optional[AsyncSession] = None

    async def __aenter__(self) -> AsyncSession:
        if _session_factory is None:
            await init_db()
        self._session = _session_factory()
        return self._session

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._session:
            if exc_type:
                await self._session.rollback()
            else:
                await self._session.commit()
            await self._session.close()
            self._session = None

