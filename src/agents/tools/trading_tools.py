"""
交易类 Agent Tools

提供组合重新平衡、单仓位调整等交易执行工具。
交易执行的底层逻辑统一在此模块中，避免各 workflow 重复实现。
"""

import asyncio
import json
from typing import Dict, List, Any
from decimal import Decimal

from langchain.tools import tool

from config import settings
from src.utils.logging_config import get_logger
from src.models.trading_models import (
    Order, Portfolio, OrderSide, OrderType, TimeInForce,
)

logger = get_logger(__name__)


def create_trading_tools(workflow) -> List[tuple]:
    """
    创建所有交易类 tools

    Args:
        workflow: WorkflowBase 子类实例

    Returns:
        [(tool_obj, "trading"), ...] 可直接传给 ToolRegistry.register_many()
    """
    return [
        (_create_rebalance_portfolio(workflow), "trading"),
        (_create_adjust_position(workflow), "trading"),
    ]


# ============================================================
# 底层交易执行（供 tools 和 workflow 共用）
# ============================================================

async def execute_single_trade(
    broker_api,
    trade: Dict[str, Any],
) -> Dict[str, Any]:
    """
    执行单笔交易

    Args:
        broker_api: BrokerAPI 实例
        trade: {"symbol", "action" ("BUY"/"SELL"), "shares", ...}

    Returns:
        {"success", "symbol", "action", "shares", "order_id"?, "error"?}
    """
    try:
        order = Order(
            symbol=trade["symbol"],
            side=OrderSide.BUY if trade["action"] == "BUY" else OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=Decimal(str(trade["shares"])),
            time_in_force=TimeInForce.DAY,
        )

        order_id = await broker_api.submit_order(order)

        if order_id:
            return {
                "success": True,
                "symbol": trade["symbol"],
                "action": trade["action"],
                "shares": trade["shares"],
                "order_id": str(order_id),
            }
        else:
            return {
                "success": False,
                "symbol": trade["symbol"],
                "action": trade["action"],
                "error": "订单提交失败",
            }
    except Exception as e:
        return {
            "success": False,
            "symbol": trade["symbol"],
            "action": trade["action"],
            "error": str(e),
        }


async def execute_rebalance_trades(
    broker_api,
    trades: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    执行重新平衡交易（先卖后买）

    Args:
        broker_api: BrokerAPI 实例
        trades: 交易列表

    Returns:
        执行结果列表
    """
    results = []
    delay = settings.rebalance_order_delay_seconds

    # 先卖出
    sell_trades = [t for t in trades if t["action"] == "SELL"]
    for trade in sell_trades:
        result = await execute_single_trade(broker_api, trade)
        results.append(result)
        if result["success"]:
            await asyncio.sleep(delay)

    # 再买入
    buy_trades = [t for t in trades if t["action"] == "BUY"]
    for trade in buy_trades:
        result = await execute_single_trade(broker_api, trade)
        results.append(result)
        if result["success"]:
            await asyncio.sleep(delay)

    return results


async def calculate_rebalance_trades(
    portfolio: Portfolio,
    target_allocations: Dict[str, float],
    market_data_api,
) -> List[Dict[str, Any]]:
    """
    计算从当前持仓到目标配置所需的交易

    Args:
        portfolio: 当前组合
        target_allocations: 目标配置 {"AAPL": 25.0, ...}（百分比）
        market_data_api: MarketDataAPI 实例

    Returns:
        交易列表
    """
    trades: List[Dict[str, Any]] = []

    min_value_threshold = Decimal(str(settings.rebalance_min_value_threshold))
    min_pct_threshold = Decimal(str(settings.rebalance_min_pct_threshold))
    buy_reserve_ratio = Decimal(str(settings.rebalance_buy_reserve_ratio))

    # 获取当前持仓
    current_positions = {
        pos.symbol: pos for pos in portfolio.positions if pos.quantity != 0
    }

    # 计算可用资金（现金 + 需要卖出的仓位市值）
    available_cash = portfolio.cash

    sell_value = Decimal("0")
    for symbol, position in current_positions.items():
        if symbol not in target_allocations:
            sell_value += position.market_value
        else:
            target_value = portfolio.equity * Decimal(str(target_allocations[symbol] / 100))
            if position.market_value > target_value:
                sell_value += (position.market_value - target_value)

    available_for_buy = available_cash + sell_value

    # 计算目标市值
    for symbol, target_pct in target_allocations.items():
        target_value = portfolio.equity * Decimal(str(target_pct / 100))

        current_position = current_positions.get(symbol)
        current_value = current_position.market_value if current_position else Decimal("0")
        current_pct = (
            (current_value / portfolio.equity * 100) if portfolio.equity > 0 else Decimal("0")
        )

        value_diff = target_value - current_value
        pct_diff = abs(target_pct - float(current_pct))

        # 检查是否超过调整阈值
        if abs(value_diff) < min_value_threshold and pct_diff < float(min_pct_threshold):
            logger.info(f"{symbol} 无需调整: 差异${value_diff:.2f} ({pct_diff:.1f}%) < 阈值")
            continue

        # 获取当前价格
        price_data = await market_data_api.get_latest_price(symbol)
        if not price_data:
            logger.warning(f"无法获取{symbol}价格，跳过")
            continue

        current_price = Decimal(str(price_data["close"]))
        if current_price <= 0:
            continue

        shares_to_trade = value_diff / current_price

        if abs(shares_to_trade) >= 1:
            action = "BUY" if shares_to_trade > 0 else "SELL"
            shares = abs(int(shares_to_trade))

            # 对于买入订单，检查是否有足够资金
            if action == "BUY":
                estimated_cost = shares * current_price
                if estimated_cost > available_for_buy * buy_reserve_ratio:
                    shares = int((available_for_buy * buy_reserve_ratio) / current_price)
                    if shares < 1:
                        logger.warning(f"资金不足，跳过{symbol}买入")
                        continue
                    available_for_buy -= shares * current_price

            trades.append({
                "symbol": symbol,
                "action": action,
                "shares": shares,
                "price": float(current_price),
                "target_pct": target_pct,
                "current_pct": float(current_pct),
                "pct_diff": pct_diff,
            })

    # 清仓不在目标配置中的股票
    for symbol, position in current_positions.items():
        if symbol not in target_allocations and position.quantity > 0:
            trades.append({
                "symbol": symbol,
                "action": "SELL",
                "shares": abs(int(position.quantity)),
                "price": 0,  # 市价
                "target_pct": 0,
                "current_pct": float(
                    (position.market_value / portfolio.equity * 100)
                ),
                "pct_diff": float(
                    (position.market_value / portfolio.equity * 100)
                ),
            })

    return trades


# ============================================================
# Tool 工厂函数
# ============================================================

def _create_rebalance_portfolio(wf):
    @tool
    async def rebalance_portfolio(
        target_allocations: Dict[str, float],
        reason: str,
    ) -> str:
        """
        执行组合重新平衡

        Args:
            target_allocations: 目标配置，例如 {"AAPL": 25.0, "MSFT": 25.0, "GOOGL": 25.0, "AMZN": 25.0}
                               - 只需指定股票/ETF的百分比，不要包含现金或"CASH"避免同名股票混淆
                               - 百分比总和可以小于100%，剩余部分自动为现金
                               - 例如: {"AAPL": 30, "MSFT": 30} 表示30%+30%+40%现金
            reason: 重新平衡的原因说明

        Returns:
            执行结果
        """
        try:
            # 检查市场状态
            market_open = await wf.is_market_open()
            if not market_open:
                warning_msg = "⚠️ 市场未开放，无法执行交易。交易计划已保存，将在下次市场开放时执行。"
                await wf.message_manager.send_message(warning_msg, "warning")
                return json.dumps({
                    "success": False,
                    "message": "市场未开放，无法执行交易",
                    "market_open": False,
                    "target_allocations": target_allocations,
                    "reason": reason,
                }, indent=2, ensure_ascii=False)

            # 过滤掉可能的现金关键词
            cash_kw = settings.get_cash_keywords()
            filtered_allocations = {
                k: v for k, v in target_allocations.items()
                if k.upper() not in cash_kw
            }

            if len(filtered_allocations) != len(target_allocations):
                removed = set(target_allocations.keys()) - set(filtered_allocations.keys())
                logger.info(f"移除了现金关键词: {removed}")
                target_allocations = filtered_allocations

            # 验证配置：总和应该≤100%
            total_pct = sum(target_allocations.values())
            if total_pct > 100:
                return f"错误: 目标配置总和为{total_pct}%，不能超过100%"

            # 计算现金比例
            cash_pct = 100 - total_pct

            # 获取当前组合
            portfolio = await wf.get_portfolio()
            if not portfolio:
                return "错误: 无法获取组合信息"

            # 通知开始重新平衡
            allocation_lines = [f"- {sym}: {pct:.1f}%" for sym, pct in target_allocations.items()]
            if cash_pct > 0:
                allocation_lines.append(f"- 💵 现金: {cash_pct:.1f}%")

            await wf.message_manager.send_message(
                f"🔄 **LLM发起组合重新平衡**\n\n"
                f"原因: {reason}\n\n"
                f"目标配置:\n" + "\n".join(allocation_lines),
                "warning",
            )

            # 计算需要执行的交易
            trades = await calculate_rebalance_trades(
                portfolio, target_allocations, wf.market_data_api,
            )

            if not trades:
                no_trade_msg = "✅ 经计算，所有仓位都在阈值范围内，无需调整"
                await wf.message_manager.send_message(no_trade_msg, "info")
                return json.dumps({
                    "success": True,
                    "message": "无需调整",
                    "trades": [],
                }, indent=2, ensure_ascii=False)

            # 执行交易
            results = await execute_rebalance_trades(wf.broker_api, trades)

            # 返回结果
            success_count = sum(1 for r in results if r["success"])
            result_msg = f"重新平衡完成: {success_count}/{len(results)} 笔交易成功"

            await wf.message_manager.send_message(
                f"✅ {result_msg}",
                "success" if success_count == len(results) else "warning",
            )

            return json.dumps({
                "success": True,
                "message": result_msg,
                "trades": results,
            }, indent=2, ensure_ascii=False, default=str)

        except Exception as e:
            logger.error(f"重新平衡失败: {e}")
            error_msg = f"错误: {str(e)}"
            await wf.message_manager.send_error(error_msg, "重新平衡")
            return error_msg

    return rebalance_portfolio


def _create_adjust_position(wf):
    @tool
    async def adjust_position(
        symbol: str,
        target_percentage: float,
        reason: str,
    ) -> str:
        """
        调整单个股票/ETF的仓位到指定百分比

        Args:
            symbol: 股票代码，如 AAPL, MSFT
            target_percentage: 目标百分比（0-100），例如 20.0 表示调整到总资产的20%
            reason: 调整原因说明

        Returns:
            调整结果
        """
        try:
            # 检查市场状态
            market_open = await wf.is_market_open()
            if not market_open:
                warning_msg = "⚠️ 市场未开放，无法执行交易"
                await wf.message_manager.send_message(warning_msg, "warning")
                return json.dumps({
                    "success": False,
                    "message": "市场未开放，无法执行交易",
                    "market_open": False,
                }, indent=2, ensure_ascii=False)

            # 参数验证
            if target_percentage < 0 or target_percentage > 100:
                return "错误: target_percentage必须在0-100之间"

            # 获取当前组合
            portfolio = await wf.get_portfolio()
            if not portfolio:
                return "错误: 无法获取组合信息"

            # 通知开始调整
            await wf.message_manager.send_message(
                f"🔧 **调整单个仓位**\n\n"
                f"股票: {symbol}\n"
                f"目标仓位: {target_percentage:.1f}%\n"
                f"原因: {reason}",
                "warning",
            )

            # 计算目标市值
            target_value = portfolio.equity * Decimal(str(target_percentage / 100))

            # 获取当前持仓
            current_position = None
            for pos in portfolio.positions:
                if pos.symbol == symbol and pos.quantity != 0:
                    current_position = pos
                    break

            current_value = current_position.market_value if current_position else Decimal("0")
            current_pct = (
                (current_value / portfolio.equity * 100) if portfolio.equity > 0 else Decimal("0")
            )

            value_diff = target_value - current_value

            # 最小调整阈值
            min_threshold = Decimal(str(settings.rebalance_min_value_threshold))
            if abs(value_diff) < min_threshold:
                no_change_msg = (
                    f"✅ {symbol} 当前仓位 {float(current_pct):.1f}%，"
                    f"与目标 {target_percentage:.1f}% 接近，无需调整"
                )
                await wf.message_manager.send_message(no_change_msg, "info")
                return json.dumps({
                    "success": True,
                    "message": "无需调整",
                    "symbol": symbol,
                    "current_percentage": float(current_pct),
                    "target_percentage": target_percentage,
                }, indent=2, ensure_ascii=False)

            # 获取当前价格
            price_data = await wf.market_data_api.get_latest_price(symbol)
            if not price_data:
                return f"错误: 无法获取{symbol}价格"

            current_price = Decimal(str(price_data["close"]))
            if current_price <= 0:
                return f"错误: {symbol}价格无效"

            # 计算需要交易的股数
            shares_to_trade = value_diff / current_price

            if abs(shares_to_trade) < 1:
                no_change_msg = f"✅ {symbol} 调整幅度过小（<1股），无需交易"
                await wf.message_manager.send_message(no_change_msg, "info")
                return json.dumps({
                    "success": True,
                    "message": "调整幅度过小，无需交易",
                    "symbol": symbol,
                    "current_percentage": float(current_pct),
                    "target_percentage": target_percentage,
                }, indent=2, ensure_ascii=False)

            # 构建交易
            action = "BUY" if shares_to_trade > 0 else "SELL"
            shares = abs(int(shares_to_trade))

            trade = {
                "symbol": symbol,
                "action": action,
                "shares": shares,
                "price": float(current_price),
                "target_pct": target_percentage,
                "current_pct": float(current_pct),
            }

            # 执行交易
            result = await execute_single_trade(wf.broker_api, trade)

            if result["success"]:
                success_msg = f"✅ {symbol} 仓位调整成功: {action} {shares}股"
                await wf.message_manager.send_message(success_msg, "success")
            else:
                error_msg = f"❌ {symbol} 仓位调整失败: {result.get('error', '未知错误')}"
                await wf.message_manager.send_message(error_msg, "error")

            return json.dumps({
                "success": result["success"],
                "symbol": symbol,
                "action": action,
                "shares": shares,
                "current_percentage": float(current_pct),
                "target_percentage": target_percentage,
                "order_id": result.get("order_id"),
                "error": result.get("error"),
            }, indent=2, ensure_ascii=False, default=str)

        except Exception as e:
            logger.error(f"调整仓位失败 {symbol}: {e}")
            error_msg = f"错误: {str(e)}"
            await wf.message_manager.send_error(error_msg, f"调整{symbol}仓位")
            return error_msg

    return adjust_position
