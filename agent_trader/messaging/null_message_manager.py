"""
Null Message Manager — 回测用静默通知

所有 send_message / send_error 等调用直接忽略，不发送任何通知。
实现 MessageManager 的完整接口，避免回测时触发 Telegram/Discord 通知。
"""

from agent_trader.utils.logging_config import get_logger

logger = get_logger(__name__)


class NullMessageManager:
    """
    回测专用 MessageManager — 所有通知静默。

    Duck-typing 兼容 MessageManager 的所有公开方法。
    """

    def __init__(self):
        self.transport = _NullTransport()

    async def send_message(self, content: str, msg_type: str = "info", **kwargs) -> bool:
        """静默发送消息"""
        return True

    async def send_error(self, error_message: str, context: str = "", **kwargs) -> bool:
        """静默发送错误"""
        return True

    async def send_alert(self, alert_type: str, message: str, **kwargs) -> bool:
        """静默发送告警"""
        return True

    async def send_portfolio_update(self, portfolio, **kwargs) -> bool:
        """静默发送组合更新"""
        return True

    async def send_order_update(self, order, **kwargs) -> bool:
        """静默发送订单更新"""
        return True

    async def start_processing(self) -> None:
        """No-op"""
        pass

    async def stop_processing(self) -> None:
        """No-op"""
        pass


class _NullTransport:
    """Null transport stub"""

    def get_transport_name(self) -> str:
        return "Null (Backtest)"

    def is_available(self) -> bool:
        return True
