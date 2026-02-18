"""
数据仓库

提供业务层面的数据访问接口
"""

from agent_trader.utils.logging_config import get_logger
from datetime import timedelta
from typing import List, Optional, Dict, Any
from decimal import Decimal

from agent_trader.utils.timezone import utc_now

from sqlalchemy import select, desc, and_, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    TradingDecision,
    AnalysisHistory,
    OrderRecord,
    PortfolioSnapshot,
    AgentMessage,
    BacktestResult,
)
from .session import get_db

logger = get_logger(__name__)


class TradingRepository:
    """
    交易数据仓库

    封装所有数据访问操作
    """

    # ========== 交易决策 ==========

    @staticmethod
    async def save_decision(
        symbol: str,
        action: str,
        quantity: Optional[Decimal] = None,
        confidence: Optional[float] = None,
        reasoning: Optional[str] = None,
        market_data: Optional[Dict] = None,
        news_sentiment: Optional[Dict] = None
    ) -> TradingDecision:
        """保存交易决策"""
        async with get_db() as db:
            decision = TradingDecision(
                symbol=symbol,
                action=action,
                quantity=quantity,
                confidence=confidence,
                reasoning=reasoning,
                market_data=market_data,
                news_sentiment=news_sentiment
            )
            db.add(decision)
            await db.flush()
            logger.info(f"保存交易决策: {symbol} {action}")
            return decision

    @staticmethod
    async def get_recent_decisions(
        symbol: Optional[str] = None,
        limit: int = 10
    ) -> List[TradingDecision]:
        """获取最近的交易决策"""
        async with get_db() as db:
            query = select(TradingDecision).order_by(desc(TradingDecision.created_at))
            if symbol:
                query = query.where(TradingDecision.symbol == symbol)
            query = query.limit(limit)
            result = await db.execute(query)
            return result.scalars().all()

    # ========== 分析历史 ==========

    @staticmethod
    async def save_analysis(
        trigger: str,
        workflow_id: Optional[str] = None,
        analysis_type: Optional[str] = None,
        input_context: Optional[Dict] = None,
        output_response: Optional[str] = None,
        tool_calls: Optional[List[str]] = None,
        trades_executed: Optional[List[Dict]] = None,
        execution_time_seconds: Optional[float] = None,
        success: bool = True,
        error_message: Optional[str] = None
    ) -> AnalysisHistory:
        """保存分析历史"""
        async with get_db() as db:
            analysis = AnalysisHistory(
                workflow_id=workflow_id,
                trigger=trigger,
                analysis_type=analysis_type,
                input_context=input_context,
                output_response=output_response,
                tool_calls=tool_calls,
                trades_executed=trades_executed,
                execution_time_seconds=execution_time_seconds,
                success=success,
                error_message=error_message
            )
            db.add(analysis)
            await db.flush()
            logger.info(f"保存分析历史: {trigger}")
            return analysis

    @staticmethod
    async def get_recent_analyses(
        trigger: Optional[str] = None,
        limit: int = 10
    ) -> List[AnalysisHistory]:
        """获取最近的分析历史"""
        async with get_db() as db:
            query = select(AnalysisHistory).order_by(desc(AnalysisHistory.created_at))
            if trigger:
                query = query.where(AnalysisHistory.trigger == trigger)
            query = query.limit(limit)
            result = await db.execute(query)
            return result.scalars().all()

    @staticmethod
    async def get_workflow_stats(analysis_type: Optional[str] = None) -> Dict[str, Any]:
        """
        从 analysis_history 聚合 workflow 运行统计。

        返回:
            {
                "total_runs": int,
                "successful_runs": int,
                "failed_runs": int,
                "last_run": str | None,       # ISO 8601
                "last_error": str | None,
            }
        """
        async with get_db() as db:
            base = select(
                sa_func.count(AnalysisHistory.id).label("total"),
                sa_func.count(
                    sa_func.nullif(AnalysisHistory.success, False)
                ).label("success"),
                sa_func.max(AnalysisHistory.created_at).label("last_run"),
            )
            if analysis_type:
                base = base.where(AnalysisHistory.analysis_type == analysis_type)

            row = (await db.execute(base)).one()
            total = row.total or 0
            success = row.success or 0
            failed = total - success
            last_run = row.last_run.isoformat() if row.last_run else None

            # 获取最近一次失败的 error_message
            last_error: Optional[str] = None
            if failed > 0:
                err_q = (
                    select(AnalysisHistory.error_message)
                    .where(AnalysisHistory.success == False)  # noqa: E712
                    .order_by(desc(AnalysisHistory.created_at))
                    .limit(1)
                )
                if analysis_type:
                    err_q = err_q.where(AnalysisHistory.analysis_type == analysis_type)
                err_row = (await db.execute(err_q)).scalar_one_or_none()
                last_error = err_row

            return {
                "total_runs": total,
                "successful_runs": success,
                "failed_runs": failed,
                "last_run": last_run,
                "last_error": last_error,
            }

    # ========== 订单记录 ==========

    @staticmethod
    async def save_order(
        symbol: str,
        side: str,
        order_type: str,
        quantity: Decimal,
        price: Optional[Decimal] = None,
        broker_order_id: Optional[str] = None,
        status: str = 'pending'
    ) -> OrderRecord:
        """保存订单"""
        async with get_db() as db:
            order = OrderRecord(
                symbol=symbol,
                side=side,
                order_type=order_type,
                quantity=quantity,
                price=price,
                broker_order_id=broker_order_id,
                status=status
            )
            db.add(order)
            await db.flush()
            logger.info(f"保存订单: {symbol} {side} {quantity}")
            return order

    @staticmethod
    async def update_order_status(
        broker_order_id: str,
        status: str,
        filled_price: Optional[Decimal] = None,
        filled_quantity: Optional[Decimal] = None,
        error_message: Optional[str] = None
    ) -> Optional[OrderRecord]:
        """更新订单状态"""
        async with get_db() as db:
            result = await db.execute(
                select(OrderRecord).where(OrderRecord.broker_order_id == broker_order_id)
            )
            order = result.scalar_one_or_none()
            if order:
                order.status = status
                if filled_price:
                    order.filled_price = filled_price
                if filled_quantity:
                    order.filled_quantity = filled_quantity
                if error_message:
                    order.error_message = error_message
                if status == 'filled':
                    order.filled_at = utc_now()
                elif status == 'cancelled':
                    order.cancelled_at = utc_now()
                logger.info(f"更新订单状态: {broker_order_id} -> {status}")
            return order

    @staticmethod
    async def get_orders(
        status: Optional[str] = None,
        symbol: Optional[str] = None,
        limit: int = 50
    ) -> List[OrderRecord]:
        """获取订单列表"""
        async with get_db() as db:
            query = select(OrderRecord).order_by(desc(OrderRecord.created_at))
            if status:
                query = query.where(OrderRecord.status == status)
            if symbol:
                query = query.where(OrderRecord.symbol == symbol)
            query = query.limit(limit)
            result = await db.execute(query)
            return result.scalars().all()

    # ========== 组合快照 ==========

    @staticmethod
    async def save_portfolio_snapshot(
        total_value: Decimal,
        cash: Decimal,
        positions_value: Decimal,
        day_pnl: Decimal,
        total_pnl: Decimal,
        positions: Optional[List[Dict]] = None
    ) -> PortfolioSnapshot:
        """保存组合快照"""
        async with get_db() as db:
            snapshot = PortfolioSnapshot(
                total_value=total_value,
                cash=cash,
                positions_value=positions_value,
                day_pnl=day_pnl,
                total_pnl=total_pnl,
                positions=positions
            )
            db.add(snapshot)
            await db.flush()
            logger.info(f"保存组合快照: ${total_value}")
            return snapshot

    @staticmethod
    async def get_portfolio_history(
        days: int = 30,
        limit: int = 100
    ) -> List[PortfolioSnapshot]:
        """获取组合历史"""
        async with get_db() as db:
            since = utc_now() - timedelta(days=days)
            query = (
                select(PortfolioSnapshot)
                .where(PortfolioSnapshot.created_at >= since)
                .order_by(desc(PortfolioSnapshot.created_at))
                .limit(limit)
            )
            result = await db.execute(query)
            return result.scalars().all()

    # ========== Agent 消息 ==========

    @staticmethod
    async def save_agent_message(
        session_id: str,
        role: str,
        content: str,
        additional_kwargs: Optional[Dict] = None
    ) -> AgentMessage:
        """保存 Agent 消息"""
        async with get_db() as db:
            msg = AgentMessage(
                session_id=session_id,
                role=role,
                content=content,
                additional_kwargs=additional_kwargs
            )
            db.add(msg)
            await db.flush()
            return msg

    @staticmethod
    async def get_agent_messages(
        session_id: str,
        limit: int = 50
    ) -> List[AgentMessage]:
        """获取 Agent 消息历史"""
        async with get_db() as db:
            query = (
                select(AgentMessage)
                .where(AgentMessage.session_id == session_id)
                .order_by(AgentMessage.created_at)
                .limit(limit)
            )
            result = await db.execute(query)
            return result.scalars().all()

    @staticmethod
    async def clear_agent_messages(session_id: str) -> int:
        """清除 Agent 消息历史"""
        from sqlalchemy import delete
        async with get_db() as db:
            result = await db.execute(
                delete(AgentMessage).where(AgentMessage.session_id == session_id)
            )
            count = result.rowcount
            logger.info(f"清除 {count} 条消息: session={session_id}")
            return count

    # ========== 回测结果 ==========

    @staticmethod
    async def save_backtest_result(
        task_id: str,
        config: Dict,
        status: str,
        result: Optional[Dict] = None,
        equity_curve: Optional[list] = None,
        trades: Optional[list] = None,
        created_at=None,
        completed_at=None,
    ) -> BacktestResult:
        """保存回测结果"""
        async with get_db() as db:
            record = BacktestResult(
                id=task_id,
                config=config,
                status=status,
                result=result,
                equity_curve=equity_curve,
                trades=trades,
                completed_at=completed_at,
            )
            # 如果已存在则更新
            existing = await db.get(BacktestResult, task_id)
            if existing:
                existing.config = config
                existing.status = status
                existing.result = result
                existing.equity_curve = equity_curve
                existing.trades = trades
                existing.completed_at = completed_at
                return existing
            else:
                db.add(record)
                await db.flush()
                return record

    @staticmethod
    async def get_backtest_results(limit: int = 50) -> list:
        """获取回测结果列表"""
        async with get_db() as db:
            query = (
                select(BacktestResult)
                .order_by(desc(BacktestResult.created_at))
                .limit(limit)
            )
            result = await db.execute(query)
            return [r.to_dict() for r in result.scalars().all()]

    @staticmethod
    async def get_backtest_result(task_id: str) -> Optional[Dict]:
        """获取单个回测结果"""
        async with get_db() as db:
            record = await db.get(BacktestResult, task_id)
            return record.to_dict() if record else None
