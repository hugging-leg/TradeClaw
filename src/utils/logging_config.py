"""
结构化日志配置

使用 structlog 提供：
- 结构化日志输出
- 请求追踪（correlation_id）
- 性能指标
- JSON 格式（生产环境）/ 彩色输出（开发环境）

使用：
    from src.utils.logging_config import setup_logging, get_logger

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

    # 共享处理器
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        add_correlation_id,
        add_service_info,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if json_logs:
        # 生产环境：JSON 格式
        processors = shared_processors + [
            structlog.processors.JSONRenderer()
        ]
        console_renderer = structlog.processors.JSONRenderer()
    else:
        # 开发环境：彩色输出
        processors = shared_processors + [
            structlog.dev.ConsoleRenderer(colors=True)
        ]
        console_renderer = structlog.dev.ConsoleRenderer(colors=True)

    # 配置 structlog
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # 配置标准 logging（用于第三方库）
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=getattr(logging, log_level),
        stream=sys.stdout,
        force=True
    )

    # 设置文件处理器
    if settings.log_to_file:
        log_dir = settings.get_log_dir()
        log_file = log_file or (log_dir / f"trading_agent_{datetime.now().strftime('%Y%m%d')}.log")

        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(getattr(logging, log_level))
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))
        logging.getLogger().addHandler(file_handler)

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

