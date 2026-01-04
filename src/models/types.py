"""
类型定义 - 使用 TypedDict 增强类型安全

提供统一的类型定义，避免使用 Dict[str, Any]
"""

from typing import TypedDict, Optional, List, Dict, Any
from datetime import datetime
from decimal import Decimal
from enum import Enum


# ========== 系统状态类型 ==========

class SystemState(str, Enum):
    """系统状态枚举"""
    INITIALIZING = "initializing"
    RUNNING = "running"
    TRADING = "trading"
    PAUSED = "paused"
    EMERGENCY = "emergency"
    STOPPED = "stopped"


class TradingSystemStatus(TypedDict):
    """交易系统状态"""
    state: str
    is_running: bool
    is_trading_enabled: bool
    is_market_open: bool
    workflow_type: str
    event_queue_size: int
    throttled_events_count: int
    last_workflow_execution: Optional[str]


class PortfolioSummary(TypedDict):
    """投资组合摘要"""
    total_equity: float
    cash: float
    cash_percentage: float
    market_value: float
    day_pnl: float
    total_positions: int


class PositionInfo(TypedDict):
    """持仓信息"""
    symbol: str
    quantity: float
    market_value: float
    percentage: float
    unrealized_pnl: float
    unrealized_pnl_pct: float


# ========== 事件类型 ==========

class EventData(TypedDict, total=False):
    """事件数据基类"""
    timestamp: str
    trigger: str
    chat_id: str
    reason: str
    context: Dict[str, Any]


class WorkflowTriggerData(TypedDict, total=False):
    """工作流触发事件数据"""
    trigger: str  # daily_rebalance, manual_analysis, llm_scheduled, realtime_rebalance
    context: Dict[str, Any]
    scheduled_by: str
    priority: int


class TradingControlData(TypedDict, total=False):
    """交易控制事件数据"""
    chat_id: str
    reason: str


class QueryEventData(TypedDict, total=False):
    """查询事件数据"""
    chat_id: str


# ========== 工作流类型 ==========

class WorkflowResult(TypedDict, total=False):
    """工作流执行结果"""
    success: bool
    workflow_type: str
    workflow_id: str
    trigger: str
    execution_time: float
    error: Optional[str]
    llm_response: Optional[str]
    trades: Optional[List[Dict[str, Any]]]


class TradeResult(TypedDict):
    """交易结果"""
    success: bool
    symbol: str
    action: str  # BUY or SELL
    shares: int
    order_id: Optional[str]
    error: Optional[str]


class RebalanceResult(TypedDict):
    """重新平衡结果"""
    success: bool
    message: str
    trades: List[TradeResult]
    target_allocations: Dict[str, float]


# ========== 市场数据类型 ==========

class MarketBar(TypedDict):
    """K线数据"""
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: int


class PriceInfo(TypedDict):
    """价格信息"""
    symbol: str
    close: float
    bid: Optional[float]
    ask: Optional[float]
    volume: Optional[int]
    timestamp: str


class MarketStatus(TypedDict):
    """市场状态"""
    is_open: bool
    next_open: Optional[str]
    next_close: Optional[str]


# ========== 新闻类型 ==========

class NewsItem(TypedDict):
    """新闻条目"""
    title: str
    description: Optional[str]
    source: str
    published_at: str
    url: str
    symbols: List[str]
    sentiment: Optional[float]


# ========== 调度类型 ==========

class ScheduledJobInfo(TypedDict):
    """调度任务信息"""
    id: str
    name: str
    next_run_time: Optional[str]
    trigger: str
    priority: str
    require_trading_day: bool
    require_market_open: bool


class SchedulerStatus(TypedDict):
    """调度器状态"""
    running: bool
    timezone: str
    exchange: str
    calendar_available: bool
    is_trading_day: bool
    is_market_open: bool
    total_jobs: int
    jobs: List[ScheduledJobInfo]


# ========== 配置类型 ==========

class BrokerConfig(TypedDict):
    """经纪商配置"""
    provider: str
    api_key: str
    secret_key: str
    base_url: str
    paper_trading: bool


class LLMConfig(TypedDict):
    """LLM 配置"""
    provider: str
    model: str
    api_key: str
    temperature: float


class TradingConfig(TypedDict):
    """交易配置"""
    max_position_size: float
    max_positions: int
    stop_loss_percentage: float
    take_profit_percentage: float
    rebalance_time: str
    portfolio_check_interval: int
    risk_check_interval: int


# ========== 消息类型 ==========

class MessageStats(TypedDict):
    """消息统计"""
    sent: int
    failed: int
    queue_size: int
    last_sent: Optional[str]


class TransportStatus(TypedDict):
    """传输层状态"""
    name: str
    initialized: bool
    available: bool
    stats: MessageStats

