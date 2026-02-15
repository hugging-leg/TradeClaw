"""
Telegram 模块

组件：
- TelegramTransport: 消息发送层
- TelegramBot: 命令处理层
- TelegramService: 组合服务（推荐使用）

使用示例:
    from src.adapters.transports.telegram import TelegramService

    service = TelegramService(trading_system=trading_system)
    await service.start()
    await service.send_message("Hello!")
"""

from .transport import TelegramTransport
from .bot import TelegramBot
from .service import TelegramService

__all__ = [
    'TelegramTransport',
    'TelegramBot',
    'TelegramService'
]
