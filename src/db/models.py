"""
SQLAlchemy 数据模型

对应 docker/postgres/init.sql 中的表结构
支持 PostgreSQL 和 SQLite 双数据库
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Any, List
import uuid

from sqlalchemy import (
    Column, String, Integer, Float, DateTime, Boolean,
    Text, JSON, Numeric, Enum as SQLEnum, ForeignKey, TypeDecorator
)
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func


class GUID(TypeDecorator):
    """
    跨数据库 UUID 类型
    - PostgreSQL: 使用原生 UUID
    - SQLite: 使用 CHAR(36) 字符串
    """
    impl = String(36)
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            from sqlalchemy.dialects.postgresql import UUID
            return dialect.type_descriptor(UUID(as_uuid=True))
        return dialect.type_descriptor(String(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if dialect.name == 'postgresql':
            return value
        if isinstance(value, uuid.UUID):
            return str(value)
        return value

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(value)


Base = declarative_base()


class TradingDecision(Base):
    """交易决策记录"""
    __tablename__ = 'trading_decisions'

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    symbol = Column(String(20), nullable=False, index=True)
    action = Column(String(10), nullable=False)  # buy, sell, hold
    quantity = Column(Numeric(20, 8), nullable=True)
    confidence = Column(Numeric(3, 2), nullable=True)
    reasoning = Column(Text, nullable=True)
    market_data = Column(JSON, nullable=True)
    news_sentiment = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': str(self.id),
            'symbol': self.symbol,
            'action': self.action,
            'quantity': float(self.quantity) if self.quantity else None,
            'confidence': float(self.confidence) if self.confidence else None,
            'reasoning': self.reasoning,
            'market_data': self.market_data,
            'news_sentiment': self.news_sentiment,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class AnalysisHistory(Base):
    """LLM 分析历史"""
    __tablename__ = 'analysis_history'

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    workflow_id = Column(String(100), nullable=True, index=True)
    trigger = Column(String(50), nullable=False)  # daily_rebalance, manual, realtime, etc.
    analysis_type = Column(String(50), nullable=True)  # market, portfolio, risk
    input_context = Column(JSON, nullable=True)  # 输入上下文
    output_response = Column(Text, nullable=True)  # LLM 响应
    tool_calls = Column(JSON, nullable=True)  # 调用的工具
    trades_executed = Column(JSON, nullable=True)  # 执行的交易
    execution_time_seconds = Column(Float, nullable=True)
    success = Column(Boolean, default=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': str(self.id),
            'workflow_id': self.workflow_id,
            'trigger': self.trigger,
            'analysis_type': self.analysis_type,
            'input_context': self.input_context,
            'output_response': self.output_response,
            'tool_calls': self.tool_calls,
            'trades_executed': self.trades_executed,
            'execution_time_seconds': self.execution_time_seconds,
            'success': self.success,
            'error_message': self.error_message,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class OrderRecord(Base):
    """订单记录"""
    __tablename__ = 'orders'

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    symbol = Column(String(20), nullable=False, index=True)
    side = Column(String(10), nullable=False)  # buy, sell
    order_type = Column(String(20), nullable=False)  # market, limit, stop, etc.
    quantity = Column(Numeric(20, 8), nullable=False)
    price = Column(Numeric(20, 8), nullable=True)
    stop_loss = Column(Numeric(20, 8), nullable=True)
    take_profit = Column(Numeric(20, 8), nullable=True)
    time_in_force = Column(String(10), default='day')
    status = Column(String(20), default='pending', index=True)
    broker_order_id = Column(String(100), nullable=True, index=True)  # Alpaca/IBKR order ID
    filled_at = Column(DateTime(timezone=True), nullable=True)
    filled_price = Column(Numeric(20, 8), nullable=True)
    filled_quantity = Column(Numeric(20, 8), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': str(self.id),
            'symbol': self.symbol,
            'side': self.side,
            'order_type': self.order_type,
            'quantity': float(self.quantity),
            'price': float(self.price) if self.price else None,
            'status': self.status,
            'broker_order_id': self.broker_order_id,
            'filled_at': self.filled_at.isoformat() if self.filled_at else None,
            'filled_price': float(self.filled_price) if self.filled_price else None,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class PortfolioSnapshot(Base):
    """组合快照"""
    __tablename__ = 'portfolio_snapshots'

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    total_value = Column(Numeric(20, 2), nullable=False)
    cash = Column(Numeric(20, 2), nullable=False)
    positions_value = Column(Numeric(20, 2), nullable=False)
    day_pnl = Column(Numeric(20, 2), nullable=False)
    total_pnl = Column(Numeric(20, 2), nullable=False)
    positions = Column(JSON, nullable=True)  # 持仓详情
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': str(self.id),
            'total_value': float(self.total_value),
            'cash': float(self.cash),
            'positions_value': float(self.positions_value),
            'day_pnl': float(self.day_pnl),
            'total_pnl': float(self.total_pnl),
            'positions': self.positions,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class AgentMessage(Base):
    """
    Agent 消息历史

    用于 LangChain Memory 持久化
    """
    __tablename__ = 'agent_messages'

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    session_id = Column(String(100), nullable=False, index=True)  # 会话 ID
    role = Column(String(20), nullable=False)  # human, ai, system, tool
    content = Column(Text, nullable=False)
    additional_kwargs = Column(JSON, nullable=True)  # 额外信息（工具调用等）
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': str(self.id),
            'session_id': self.session_id,
            'role': self.role,
            'content': self.content,
            'additional_kwargs': self.additional_kwargs,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

