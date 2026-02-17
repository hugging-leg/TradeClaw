"""
结构化日志配置

使用 structlog 提供：
- 结构化日志输出
- 请求追踪（correlation_id）
- 性能指标
- JSON 格式（生产环境）/ 彩色输出（开发环境）

使用：
    from agent_trader.utils.logging_config import setup_logging, get_logger

    setup_logging()  # 在 main.py 调用一次
    logger = get_logger(__name__)

    logger.info("事件发生", symbol="AAPL", action="buy", quantity=100)
"""

import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional
import uuid

import structlog
from structlog.types import Processor

from config import settings


# 全局 correlation_id（用于追踪请求链）
_correlation_id: Optional[str] = None


def get_correlation_id() -> str:
    """获取当前 correlation_id"""
    global _correlation_id
    if _correlation_id is None:
        _correlation_id = str(uuid.uuid4())[:8]
    return _correlation_id


def set_correlation_id(cid: str):
    """设置 correlation_id（用于追踪事件链）"""
    global _correlation_id
    _correlation_id = cid


def reset_correlation_id():
    """重置 correlation_id"""
    global _correlation_id
    _correlation_id = str(uuid.uuid4())[:8]


def add_correlation_id(
    logger: logging.Logger,
    method_name: str,
    event_dict: dict
) -> dict:
    """添加 correlation_id 到日志"""
    event_dict["correlation_id"] = get_correlation_id()
    return event_dict


def add_service_info(
    logger: logging.Logger,
    method_name: str,
    event_dict: dict
) -> dict:
    """添加服务信息"""
    event_dict["service"] = "trading-agent"
    event_dict["environment"] = settings.environment
    return event_dict


def setup_logging(
    log_level: Optional[str] = None,
    json_logs: Optional[bool] = None,
    log_file: Optional[Path] = None
):
    """
    配置结构化日志

    Args:
        log_level: 日志级别，默认从 settings 读取
        json_logs: 是否输出 JSON 格式，生产环境默认 True
        log_file: 日志文件路径，默认从 settings 读取
    """
    log_level = log_level or settings.log_level.upper()
    is_production = settings.environment == "production"
    json_logs = json_logs if json_logs is not None else is_production
    level = getattr(logging, log_level)

    # 配置标准 logging handlers
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # 清除现有 handlers
    root_logger.handlers.clear()

    # 控制台 handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)

    # 文件 handler
    file_handler = None
    if settings.log_to_file:
        log_dir = settings.get_log_dir()
        log_file_path = log_file or (
            log_dir / f"trading_agent_{datetime.now().strftime('%Y%m%d')}.log"
        )
        file_handler = logging.FileHandler(log_file_path, encoding='utf-8')
        file_handler.setLevel(level)

    # 共享处理器（structlog 处理链）
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        add_correlation_id,
        add_service_info,
        structlog.processors.StackInfoRenderer(),
        # 将 structlog 事件转换为标准 logging
        structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
    ]

    # 控制台格式化器
    if json_logs:
        console_formatter = structlog.stdlib.ProcessorFormatter(
            processor=structlog.processors.JSONRenderer(),
            foreign_pre_chain=shared_processors[:-1],
        )
    else:
        console_formatter = structlog.stdlib.ProcessorFormatter(
            processor=structlog.dev.ConsoleRenderer(colors=True),
            foreign_pre_chain=shared_processors[:-1],
        )
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # 文件格式化器（可读格式，无颜色）
    if file_handler:
        file_formatter = structlog.stdlib.ProcessorFormatter(
            processor=structlog.dev.ConsoleRenderer(colors=False),
            foreign_pre_chain=shared_processors[:-1],
        )
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)

    # 配置 structlog 使用标准库
    structlog.configure(
        processors=shared_processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # 降低第三方库日志级别
    for lib in ["httpx", "urllib3", "telegram", "aiohttp", "asyncio"]:
        logging.getLogger(lib).setLevel(logging.WARNING)

    # 返回配置的 logger
    return get_logger("trading_agent")


def get_logger(name: str = None) -> structlog.BoundLogger:
    """
    获取 structlog logger

    Args:
        name: logger 名称

    Returns:
        结构化 logger
    """
    return structlog.get_logger(name)


class LoggerMixin:
    """
    Logger Mixin

    为类提供 self.logger 属性

    使用：
        class MyService(LoggerMixin):
            def do_something(self):
                self.logger.info("doing something", param=123)
    """

    @property
    def logger(self) -> structlog.BoundLogger:
        if not hasattr(self, '_logger'):
            self._logger = get_logger(self.__class__.__name__)
        return self._logger


# 便捷函数
def log_trade(
    action: str,
    symbol: str,
    quantity: float,
    price: Optional[float] = None,
    **kwargs
):
    """记录交易日志"""
    logger = get_logger("trades")
    logger.info(
        "trade_executed",
        action=action,
        symbol=symbol,
        quantity=quantity,
        price=price,
        **kwargs
    )


def log_workflow(
    workflow_type: str,
    workflow_id: str,
    status: str,
    duration_seconds: Optional[float] = None,
    **kwargs
):
    """记录工作流日志"""
    logger = get_logger("workflow")
    logger.info(
        "workflow_event",
        workflow_type=workflow_type,
        workflow_id=workflow_id,
        status=status,
        duration_seconds=duration_seconds,
        **kwargs
    )


def log_api_call(
    provider: str,
    endpoint: str,
    status_code: int,
    duration_ms: float,
    **kwargs
):
    """记录 API 调用日志"""
    logger = get_logger("api")
    level = "info" if status_code < 400 else "error"
    getattr(logger, level)(
        "api_call",
        provider=provider,
        endpoint=endpoint,
        status_code=status_code,
        duration_ms=duration_ms,
        **kwargs
    )

