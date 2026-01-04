"""
Trading Workflow 基类

只定义真正需要的接口：
- run_workflow: 执行工作流（必须实现）
- get_workflow_type: 获取类型（有默认实现）

其他方法为通用工具方法，子类按需使用。
"""

from src.utils.logging_config import get_logger
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from datetime import datetime

from src.interfaces.broker_api import BrokerAPI
from src.interfaces.market_data_api import MarketDataAPI
from src.interfaces.news_api import NewsAPI
from src.interfaces.factory import (
    get_broker_api, get_market_data_api, get_news_api
)
from src.messaging.message_manager import MessageManager
from src.models.trading_models import TradingDecision, Portfolio

logger = get_logger(__name__)


class WorkflowBase(ABC):
    """
    Trading Workflow 基类

    子类只需实现:
    - run_workflow(): 执行工作流
    """

    def __init__(
        self,
        broker_api: BrokerAPI = None,
        market_data_api: MarketDataAPI = None,
        news_api: NewsAPI = None,
        message_manager: MessageManager = None
    ):
        if message_manager is None:
            raise ValueError("MessageManager is required")

        self.broker_api = broker_api or get_broker_api()
        self.market_data_api = market_data_api or get_market_data_api()
        self.news_api = news_api or get_news_api()
        self.message_manager = message_manager

        # 状态
        self.is_running = False
        self.current_portfolio: Optional[Portfolio] = None

        # 统计
        self.stats = {
            'total_runs': 0,
            'successful_runs': 0,
            'failed_runs': 0,
            'last_run': None,
            'last_error': None
        }

        logger.info(f"Initialized {self.__class__.__name__}")

    @abstractmethod
    async def run_workflow(
        self,
        trigger_reason: str = "scheduled",
        **kwargs
    ) -> TradingDecision:
        """
        执行工作流

        Args:
            trigger_reason: 触发原因
            **kwargs: 其他参数

        Returns:
            TradingDecision
        """
        pass

    def get_workflow_type(self) -> str:
        """获取工作流类型"""
        # 从类的 _workflow_metadata 获取，或使用类名
        meta = getattr(self, '_workflow_metadata', {})
        return meta.get('type', self.__class__.__name__.lower())

    # ========== 通用工具方法 ==========

    async def get_portfolio(self) -> Optional[Portfolio]:
        """获取当前组合"""
        try:
            return await self.broker_api.get_portfolio()
        except Exception as e:
            logger.error(f"获取组合失败: {e}")
            return None

    async def get_market_data(self) -> Dict[str, Any]:
        """获取市场数据"""
        try:
            return await self.market_data_api.get_market_overview()
        except Exception as e:
            logger.error(f"获取市场数据失败: {e}")
            return {}

    async def get_news(self, limit: int = 20) -> List[Dict[str, Any]]:
        """获取新闻"""
        try:
            news_items = await self.news_api.get_market_overview_news(limit=limit)
            return [
                {
                    "title": item.title,
                    "description": item.description or "",
                    "source": item.source,
                    "published_at": item.published_at.isoformat(),
                    "symbols": item.symbols
                }
                for item in news_items
            ]
        except Exception as e:
            logger.error(f"获取新闻失败: {e}")
            return []

    async def is_market_open(self) -> bool:
        """检查市场是否开盘"""
        try:
            return await self.broker_api.is_market_open()
        except Exception as e:
            logger.error(f"检查市场状态失败: {e}")
            return False

    async def send_notification(self, message: str, msg_type: str = "info"):
        """发送通知"""
        await self.message_manager.send_message(message, msg_type)

    def update_stats(self, success: bool, error: Optional[str] = None):
        """更新统计"""
        self.stats['total_runs'] += 1
        self.stats['last_run'] = datetime.now().isoformat()

        if success:
            self.stats['successful_runs'] += 1
        else:
            self.stats['failed_runs'] += 1
            self.stats['last_error'] = error

    # ========== 工作流生命周期方法 ==========

    def _generate_workflow_id(self) -> str:
        """生成工作流 ID"""
        return f"{self.get_workflow_type()}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    async def send_workflow_start_notification(self, workflow_name: str):
        """发送工作流开始通知"""
        message = f"🚀 **{workflow_name} Workflow Started**\n\n"
        message += f"Starting AI trading analysis at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        await self.send_notification(message, "info")

    async def send_workflow_complete_notification(self, workflow_name: str, execution_time: float):
        """发送工作流完成通知"""
        message = f"✅ **{workflow_name} Workflow Complete**\n\n"
        message += f"Trading analysis completed in {execution_time:.2f} seconds."
        await self.send_notification(message, "success")

    async def _handle_workflow_error(self, error: Exception, stage: str) -> Dict[str, Any]:
        """处理工作流错误"""
        error_message = f"Error in {stage}: {str(error)}"
        logger.error(error_message)
        await self.message_manager.send_error(error_message, stage)

        return {
            "success": False,
            "error": error_message,
            "stage": stage,
            "workflow_type": self.get_workflow_type()
        }
