"""
回测运行器

核心设计：
- 事件驱动：按照 workflow 的实际调度时间线推进（而非固定日推进）
- 时间隔离：通过 contextvars SimulatedClock 注入模拟时间，utc_now() 自动返回
- 记忆隔离：使用 InMemoryStore + MemorySaver，回测结束自动释放
- 数据隔离：PaperBroker + BacktestMarketData + BacktestNews + NullMessageManager
- Agent 零改动：所有 tools 通过接口层委托，不感知回测

时间线推进逻辑：
1. 生成 [start_date, end_date] 范围内的交易日列表
2. 对每个交易日，在 09:30 ET 设置模拟时间，调用 workflow.execute()
3. 每天结束后记录 equity snapshot
4. 通过 SSE 推送进度和 equity 数据
5. 全部完成后计算统计指标并持久化
"""

import asyncio
import uuid
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, time as dtime
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Callable, Awaitable

from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore

from agent_trader.adapters.brokers.paper_broker import PaperBrokerAdapter
from agent_trader.adapters.market_data.backtest_market_data import BacktestMarketDataAdapter
from agent_trader.adapters.news.backtest_news_adapter import BacktestNewsAdapter
from agent_trader.agents.workflow_factory import WorkflowFactory
from agent_trader.agents.workflow_base import event_broadcaster
from agent_trader.messaging.null_message_manager import NullMessageManager
from agent_trader.utils.logging_config import get_logger
from agent_trader.utils.timezone import (
    utc_now, set_simulated_time, clear_simulated_time, UTC,
    get_trading_timezone,
)

logger = get_logger(__name__)


# ============================================================
# 交易日历工具
# ============================================================

def _get_trading_days(start: datetime, end: datetime, exchange: str = "XNYS") -> List[datetime]:
    """
    使用 exchange_calendars 获取 [start, end] 范围内的精确交易日列表。

    正确处理节假日（如 MLK Day、感恩节、圣诞节等），不是简单排除周末。

    Args:
        start: 起始日期（UTC aware datetime）
        end: 结束日期（UTC aware datetime）
        exchange: 交易所代码，默认 XNYS (NYSE)

    Returns:
        交易日列表，每个元素是 UTC datetime，时间设为该日 09:30 交易时区。
    """
    import pandas as pd
    from agent_trader.utils.time_utils import get_calendar

    trading_tz = get_trading_timezone()
    market_open = dtime(9, 30)

    start_date = start.date() if isinstance(start, datetime) else start
    end_date = end.date() if isinstance(end, datetime) else end

    calendar = get_calendar(exchange)

    # exchange_calendars.sessions 返回 DatetimeIndex，筛选范围
    sessions = calendar.sessions_in_range(
        pd.Timestamp(start_date),
        pd.Timestamp(end_date),
    )

    days = []
    for session in sessions:
        # session 是 pd.Timestamp (date only)，转为交易时区 09:30 再转 UTC
        local_dt = trading_tz.localize(
            datetime.combine(session.date(), market_open)
        )
        utc_dt = local_dt.astimezone(UTC)
        days.append(utc_dt)

    return days


# ============================================================
# 回测配置
# ============================================================

@dataclass
class BacktestConfig:
    """回测配置（前端可编辑的参数）"""
    start_date: str  # YYYY-MM-DD
    end_date: str  # YYYY-MM-DD
    initial_capital: float = 100_000.0
    workflow_type: str = "llm_portfolio"
    commission_rate: float = 0.001  # 0.1%
    slippage_bps: float = 5.0  # 5 bps = 0.05%
    # 调度：每 N 个交易日执行一次 workflow
    run_interval_days: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "start_date": self.start_date,
            "end_date": self.end_date,
            "initial_capital": self.initial_capital,
            "workflow_type": self.workflow_type,
            "commission_rate": self.commission_rate,
            "slippage_bps": self.slippage_bps,
            "run_interval_days": self.run_interval_days,
        }


# ============================================================
# 回测任务状态
# ============================================================

class BacktestStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class BacktestTask:
    """回测任务状态"""
    id: str
    config: BacktestConfig
    status: BacktestStatus = BacktestStatus.PENDING
    progress: float = 0.0  # 0~1
    current_date: Optional[str] = None
    equity_curve: List[Dict[str, Any]] = field(default_factory=list)
    trades: List[Dict[str, Any]] = field(default_factory=list)
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    created_at: datetime = field(default_factory=utc_now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    _cancel_event: asyncio.Event = field(default_factory=asyncio.Event, repr=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "config": self.config.to_dict(),
            "status": self.status.value,
            "progress": self.progress,
            "current_date": self.current_date,
            "equity_curve": self.equity_curve,
            "trades": self.trades,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


# ============================================================
# 统计指标计算
# ============================================================

def _compute_statistics(
    equity_curve: List[Dict[str, Any]],
    trades: List[Dict[str, Any]],
    initial_capital: float,
) -> Dict[str, Any]:
    """计算回测统计指标"""
    if not equity_curve:
        return {
            "total_return": 0.0,
            "annualized_return": 0.0,
            "sharpe_ratio": 0.0,
            "max_drawdown": 0.0,
            "win_rate": 0.0,
            "total_trades": 0,
            "profit_factor": 0.0,
            "avg_trade_pnl": 0.0,
        }

    equities = [pt["equity"] for pt in equity_curve]
    final_equity = equities[-1]
    total_return = (final_equity - initial_capital) / initial_capital

    # 年化收益
    n_days = len(equities)
    annualized_return = (1 + total_return) ** (252 / max(n_days, 1)) - 1 if total_return > -1 else -1.0

    # 日收益率
    daily_returns = []
    for i in range(1, len(equities)):
        if equities[i - 1] > 0:
            daily_returns.append(equities[i] / equities[i - 1] - 1)

    # Sharpe Ratio (假设无风险利率 = 0)
    if daily_returns:
        mean_r = sum(daily_returns) / len(daily_returns)
        std_r = (sum((r - mean_r) ** 2 for r in daily_returns) / len(daily_returns)) ** 0.5
        sharpe_ratio = (mean_r / std_r * math.sqrt(252)) if std_r > 0 else 0.0
    else:
        sharpe_ratio = 0.0

    # 最大回撤
    peak = equities[0]
    max_dd = 0.0
    for eq in equities:
        if eq > peak:
            peak = eq
        dd = (peak - eq) / peak if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd

    # 交易统计
    total_trades_count = len(trades)
    if total_trades_count > 0:
        # 简化：按 sell 交易计算 PnL
        sell_trades = [t for t in trades if t.get("side") == "sell"]
        winning = sum(1 for t in sell_trades if t.get("pnl", 0) >= 0)
        win_rate = winning / len(sell_trades) if sell_trades else 0.0

        gross_profit = sum(t.get("pnl", 0) for t in sell_trades if t.get("pnl", 0) > 0)
        gross_loss = abs(sum(t.get("pnl", 0) for t in sell_trades if t.get("pnl", 0) < 0))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf") if gross_profit > 0 else 0.0

        total_pnl = sum(t.get("pnl", 0) for t in sell_trades)
        avg_trade_pnl = total_pnl / len(sell_trades) if sell_trades else 0.0
    else:
        win_rate = 0.0
        profit_factor = 0.0
        avg_trade_pnl = 0.0

    return {
        "total_return": round(total_return, 6),
        "annualized_return": round(annualized_return, 6),
        "sharpe_ratio": round(sharpe_ratio, 4),
        "max_drawdown": round(max_dd, 6),
        "win_rate": round(win_rate, 4),
        "total_trades": total_trades_count,
        "profit_factor": round(profit_factor, 4),
        "avg_trade_pnl": round(avg_trade_pnl, 2),
        "final_equity": round(final_equity, 2),
        "initial_capital": initial_capital,
    }


# ============================================================
# BacktestRunner
# ============================================================

class BacktestRunner:
    """
    回测运行管理器

    - 接受回测请求，分配 task_id
    - 在当前 event loop 中异步执行（workflow 本身是 async 的）
    - 通过 SSE event_broadcaster 推送实时进度
    - 维护任务状态，供 API 查询
    """

    def __init__(self, real_market_data=None, max_concurrent: int = 2):
        """
        Args:
            real_market_data: 真实的 MarketDataAPI 实例（用于拉取历史数据）
            max_concurrent: 最大并发回测数
        """
        self._real_market_data = real_market_data
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._tasks: Dict[str, BacktestTask] = {}
        self._max_tasks = 50
        self._running_tasks: Dict[str, asyncio.Task] = {}

    def set_real_market_data(self, api) -> None:
        """延迟注入真实 MarketDataAPI"""
        self._real_market_data = api

    async def submit(self, config: BacktestConfig) -> str:
        """
        提交回测任务

        Returns:
            task_id
        """
        task_id = str(uuid.uuid4())[:8]
        task = BacktestTask(id=task_id, config=config)
        self._tasks[task_id] = task

        self._cleanup_old_tasks()

        # 在当前 event loop 中启动异步任务
        asyncio_task = asyncio.create_task(self._run_backtest(task_id))
        self._running_tasks[task_id] = asyncio_task

        logger.info("Backtest submitted: %s (workflow=%s, %s ~ %s)",
                     task_id, config.workflow_type, config.start_date, config.end_date)
        return task_id

    def cancel(self, task_id: str) -> bool:
        """取消回测任务"""
        task = self._tasks.get(task_id)
        if not task or task.status != BacktestStatus.RUNNING:
            return False
        task._cancel_event.set()
        return True

    async def _run_backtest(self, task_id: str) -> None:
        """执行单个回测任务"""
        task = self._tasks[task_id]
        config = task.config

        async with self._semaphore:
            task.status = BacktestStatus.RUNNING
            task.started_at = utc_now()
            self._emit_progress(task)

            try:
                await self._execute_backtest(task)
            except asyncio.CancelledError:
                task.status = BacktestStatus.CANCELLED
                task.error = "Cancelled by user"
                logger.info("Backtest cancelled: %s", task_id)
            except Exception as e:
                task.status = BacktestStatus.FAILED
                task.error = str(e)
                logger.error("Backtest failed: %s - %s", task_id, e, exc_info=True)
            finally:
                task.completed_at = utc_now()
                clear_simulated_time()
                self._running_tasks.pop(task_id, None)
                self._emit_progress(task)

    async def _execute_backtest(self, task: BacktestTask) -> None:
        """核心回测执行逻辑"""
        config = task.config

        # 1. 解析日期
        start_dt = datetime.strptime(config.start_date, "%Y-%m-%d").replace(tzinfo=UTC)
        end_dt = datetime.strptime(config.end_date, "%Y-%m-%d").replace(tzinfo=UTC)

        # 2. 生成交易日列表
        trading_days = _get_trading_days(start_dt, end_dt)
        if not trading_days:
            raise ValueError(f"No trading days in range {config.start_date} ~ {config.end_date}")

        logger.info("Backtest %s: %d trading days, interval=%d",
                     task.id, len(trading_days), config.run_interval_days)

        # 3. 获取真实 MarketDataAPI
        if self._real_market_data is None:
            from agent_trader.interfaces.factory import get_market_data_api
            self._real_market_data = get_market_data_api()

        # 4. 创建回测专用适配器
        bt_market_data = BacktestMarketDataAdapter(
            real_market_data=self._real_market_data,
            backtest_start=start_dt,
            backtest_end=end_dt,
        )

        bt_broker = PaperBrokerAdapter(
            initial_capital=config.initial_capital,
            commission_rate=config.commission_rate,
            slippage_bps=config.slippage_bps,
        )

        # 设置 price_provider：PaperBroker 通过 BacktestMarketData 获取价格
        async def _price_provider(symbol: str):
            return await bt_market_data.get_latest_price(symbol)

        bt_broker._price_provider = _price_provider

        # 获取真实 NewsAPI 用于历史新闻（防 lookahead 由 adapter 内部处理）
        try:
            from agent_trader.interfaces.factory import get_news_api
            real_news = get_news_api()
        except Exception:
            real_news = None
            logger.warning("Backtest %s: no real news API available, news will be empty", task.id)

        bt_news = BacktestNewsAdapter(
            real_news_api=real_news,
            backtest_start=start_dt,
            backtest_end=end_dt,
        )
        bt_message = NullMessageManager()

        # 5. 创建隔离的 memory
        checkpointer = MemorySaver()
        store = InMemoryStore()

        # 6. 创建 workflow 实例
        workflow = WorkflowFactory.create_workflow(
            workflow_type=config.workflow_type,
            broker_api=bt_broker,
            market_data_api=bt_market_data,
            news_api=bt_news,
            message_manager=bt_message,
            checkpointer=checkpointer,
            store=store,
        )

        # 禁用 _trading_system 引用（回测中不支持 self-scheduling）
        workflow._trading_system = None

        # 启用回测模式：策略持仓使用内存后端，不污染实盘 DB
        workflow._backtest_mode = True

        # 7. 记录初始 equity
        task.equity_curve.append({
            "date": config.start_date,
            "equity": config.initial_capital,
            "cash": config.initial_capital,
            "positions_value": 0.0,
        })

        # 8. 按交易日推进
        execution_days = trading_days[::config.run_interval_days]
        prev_trade_count = 0  # 追踪已推送的 trades 数量

        for i, day in enumerate(execution_days):
            # 检查取消
            if task._cancel_event.is_set():
                task.status = BacktestStatus.CANCELLED
                break

            # 设置模拟时间
            set_simulated_time(day)
            date_str = day.strftime("%Y-%m-%d")
            task.current_date = date_str

            logger.info(
                "Backtest %s: day %d/%d = %s (simulated_time=%s)",
                task.id, i + 1, len(execution_days), date_str,
                day.isoformat(),
            )

            trades_before = len(bt_broker.get_trades())

            try:
                # 执行 workflow
                result = await workflow.execute(initial_context={
                    "trigger": "backtest",
                    "backtest_id": task.id,
                    "simulated_date": date_str,
                })

                # 调试：输出 workflow 执行结果摘要
                if result and isinstance(result, dict):
                    buy_results = result.get("buy_results", [])
                    sold = result.get("sold_positions", [])
                    tool_calls = result.get("tool_calls", [])
                    logger.info(
                        "Backtest %s [%s]: workflow done — tools=%d, buy_signals=%d, sold=%d",
                        task.id, date_str, len(tool_calls), len(buy_results), len(sold),
                    )
                    if buy_results:
                        for br in buy_results:
                            logger.info(
                                "Backtest %s [%s]:   buy_signal: %s success=%s reason=%s",
                                task.id, date_str,
                                br.get("ticker"), br.get("success"), br.get("reason", ""),
                            )
                else:
                    logger.info(
                        "Backtest %s [%s]: workflow returned %s",
                        task.id, date_str, type(result).__name__,
                    )

            except Exception as e:
                logger.warning(
                    "Backtest %s: workflow error on %s: %s",
                    task.id, date_str, e,
                    exc_info=True,
                )
                # 继续下一天，不中断回测

            # 设置收盘时间（16:00 ET → ~21:00 UTC）
            close_time = day.replace(
                hour=day.hour + 7,  # 09:30 + 6.5h ≈ 16:00
                minute=0,
            )
            set_simulated_time(close_time)

            # 记录当日 equity
            equity = float(await bt_broker._calc_equity())
            cash = float(bt_broker._cash)
            positions_value = equity - cash

            trades_after = len(bt_broker.get_trades())
            new_trade_count = trades_after - trades_before

            logger.info(
                "Backtest %s [%s]: equity=%.2f cash=%.2f positions=%.2f new_trades=%d total_trades=%d",
                task.id, date_str, equity, cash, positions_value,
                new_trade_count, trades_after,
            )

            task.equity_curve.append({
                "date": date_str,
                "equity": round(equity, 2),
                "cash": round(cash, 2),
                "positions_value": round(positions_value, 2),
            })

            # 收集本轮新增 trades
            all_trades = bt_broker.get_trades()
            new_trades = all_trades[prev_trade_count:]
            task.trades = all_trades
            prev_trade_count = len(all_trades)

            # 更新进度（含实时 equity + trades）
            task.progress = (i + 1) / len(execution_days)
            self._emit_progress(task, new_trades=new_trades)

        # 10. 计算统计指标
        stats = _compute_statistics(
            task.equity_curve,
            task.trades,
            config.initial_capital,
        )
        task.result = stats

        if task.status != BacktestStatus.CANCELLED:
            task.status = BacktestStatus.COMPLETED
            task.progress = 1.0

        # 11. 持久化到 DB
        await self._persist_result(task)

        logger.info(
            "Backtest %s completed: return=%.2f%% sharpe=%.2f max_dd=%.2f%% trades=%d",
            task.id,
            stats["total_return"] * 100,
            stats["sharpe_ratio"],
            stats["max_drawdown"] * 100,
            stats["total_trades"],
        )

    def _emit_progress(self, task: BacktestTask, new_trades: Optional[List[Dict[str, Any]]] = None) -> None:
        """通过 SSE 推送回测进度（含完整 equity_curve + 增量 trades）"""
        event_broadcaster.emit({
            "event": "backtest_progress",
            "data": {
                "task_id": task.id,
                "status": task.status.value,
                "progress": task.progress,
                "current_date": task.current_date,
                "equity_curve": task.equity_curve,  # 推送完整曲线
                "latest_equity": task.equity_curve[-1] if task.equity_curve else None,
                "trades": task.trades,  # 推送完整 trades 列表
                "new_trades": new_trades or [],  # 本轮新增的 trades
                "error": task.error,
                "result": task.result,  # 完成时包含统计
            },
        })

    async def _persist_result(self, task: BacktestTask) -> None:
        """持久化回测结果到数据库"""
        try:
            from agent_trader.utils.db_utils import DB_AVAILABLE, get_trading_repository
            if not DB_AVAILABLE:
                logger.debug("DB not available, skipping backtest persistence")
                return

            repo = get_trading_repository()
            if repo and hasattr(repo, "save_backtest_result"):
                await repo.save_backtest_result(
                    task_id=task.id,
                    config=task.config.to_dict(),
                    status=task.status.value,
                    result=task.result,
                    equity_curve=task.equity_curve,
                    trades=task.trades,
                    created_at=task.created_at,
                    completed_at=task.completed_at,
                )
                logger.info("Backtest %s persisted to DB", task.id)
        except Exception as e:
            logger.warning("Failed to persist backtest %s: %s", task.id, e)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_task(self, task_id: str) -> Optional[BacktestTask]:
        """获取任务状态"""
        return self._tasks.get(task_id)

    def get_all_tasks(self) -> List[dict]:
        """获取所有任务"""
        return [t.to_dict() for t in sorted(
            self._tasks.values(),
            key=lambda t: t.created_at,
            reverse=True,
        )]

    def _cleanup_old_tasks(self):
        """清理过多的历史任务"""
        if len(self._tasks) > self._max_tasks:
            sorted_ids = sorted(
                self._tasks.keys(),
                key=lambda tid: self._tasks[tid].created_at,
            )
            to_remove = sorted_ids[: len(sorted_ids) - self._max_tasks]
            for tid in to_remove:
                if self._tasks[tid].status in (
                    BacktestStatus.COMPLETED,
                    BacktestStatus.FAILED,
                    BacktestStatus.CANCELLED,
                ):
                    del self._tasks[tid]

    def shutdown(self):
        """关闭所有运行中的回测"""
        for task_id, asyncio_task in self._running_tasks.items():
            asyncio_task.cancel()
        self._running_tasks.clear()
        logger.info("BacktestRunner shutdown")
