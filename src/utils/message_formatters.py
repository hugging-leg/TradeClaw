"""
消息格式化工具

用于格式化各种交易相关消息
"""

from typing import Optional, Dict, Any, List
from decimal import Decimal
from datetime import datetime


def format_order_message(order, event_type: str) -> str:
    """
    格式化订单消息

    Args:
        order: 订单对象
        event_type: 事件类型（created, filled, cancelled, rejected）

    Returns:
        格式化的消息字符串
    """
    emoji_map = {
        'created': '📝',
        'filled': '✅',
        'cancelled': '❌',
        'rejected': '⚠️',
        'partial': '📊'
    }
    emoji = emoji_map.get(event_type, '📌')

    # 基本信息
    symbol = getattr(order, 'symbol', 'N/A')
    side = getattr(order, 'side', 'N/A')
    if hasattr(side, 'value'):
        side = side.value
    quantity = getattr(order, 'quantity', 0)
    order_type = getattr(order, 'order_type', 'N/A')
    if hasattr(order_type, 'value'):
        order_type = order_type.value

    message = f"{emoji} **订单{_get_event_text(event_type)}**\n\n"
    message += f"• 股票: `{symbol}`\n"
    message += f"• 方向: {side}\n"
    message += f"• 数量: {quantity}\n"
    message += f"• 类型: {order_type}\n"

    # 价格信息
    if hasattr(order, 'price') and order.price:
        message += f"• 价格: ${order.price}\n"

    if hasattr(order, 'filled_price') and order.filled_price:
        message += f"• 成交价: ${order.filled_price}\n"

    # 订单 ID
    if hasattr(order, 'id') and order.id:
        message += f"\n_订单 ID: {order.id[:8]}..._"

    return message


def format_portfolio_message(portfolio) -> str:
    """
    格式化投资组合消息

    Args:
        portfolio: 投资组合对象

    Returns:
        格式化的消息字符串
    """
    message = "📊 **投资组合概览**\n\n"

    # 账户摘要
    equity = getattr(portfolio, 'equity', Decimal('0'))
    cash = getattr(portfolio, 'cash', Decimal('0'))
    market_value = getattr(portfolio, 'market_value', Decimal('0'))
    total_pnl = getattr(portfolio, 'total_pnl', Decimal('0'))

    message += f"💰 **账户信息**\n"
    message += f"• 总权益: ${equity:,.2f}\n"
    message += f"• 现金: ${cash:,.2f}\n"
    message += f"• 市值: ${market_value:,.2f}\n"

    pnl_emoji = "📈" if total_pnl >= 0 else "📉"
    message += f"• 总盈亏: {pnl_emoji} ${total_pnl:+,.2f}\n"

    # 持仓列表
    positions = getattr(portfolio, 'positions', [])
    if positions:
        message += f"\n📋 **持仓 ({len(positions)})**\n"
        for pos in positions[:10]:  # 最多显示 10 个
            symbol = getattr(pos, 'symbol', 'N/A')
            qty = getattr(pos, 'quantity', 0)
            pnl = getattr(pos, 'unrealized_pnl', Decimal('0'))
            pnl_pct = getattr(pos, 'unrealized_pnl_percentage', Decimal('0'))

            pnl_emoji = "🟢" if pnl >= 0 else "🔴"
            message += f"• `{symbol}`: {qty} 股 {pnl_emoji} {pnl_pct:+.1f}%\n"

        if len(positions) > 10:
            message += f"_... 还有 {len(positions) - 10} 个持仓_\n"
    else:
        message += "\n_无持仓_\n"

    return message


def format_alert_message(message: str, alert_type: str = "info") -> str:
    """
    格式化系统警报消息

    Args:
        message: 警报内容
        alert_type: 警报类型（info, warning, error, success）

    Returns:
        格式化的消息字符串
    """
    emoji_map = {
        'info': 'ℹ️',
        'warning': '⚠️',
        'error': '🚨',
        'success': '✅',
        'critical': '🔴'
    }
    emoji = emoji_map.get(alert_type, 'ℹ️')

    return f"{emoji} **系统通知**\n\n{message}"


def format_status_message(status: Dict[str, Any]) -> str:
    """
    格式化系统状态消息

    Args:
        status: 状态字典

    Returns:
        格式化的消息字符串
    """
    message = "🤖 **系统状态**\n\n"

    # 系统状态
    state = status.get('state', 'unknown')
    is_running = status.get('is_running', False)
    is_trading = status.get('is_trading_enabled', False)
    is_market_open = status.get('is_market_open', False)

    state_emoji = "🟢" if is_running else "🔴"
    trading_emoji = "✅" if is_trading else "⏸️"
    market_emoji = "🔔" if is_market_open else "🔕"

    message += f"{state_emoji} 状态: {state}\n"
    message += f"{trading_emoji} 交易: {'已启用' if is_trading else '已暂停'}\n"
    message += f"{market_emoji} 市场: {'开盘中' if is_market_open else '已休市'}\n"

    # 工作流信息
    workflow_type = status.get('workflow_type', 'N/A')
    message += f"\n📋 工作流: {workflow_type}\n"

    # 事件队列
    queue_size = status.get('event_queue_size', 0)
    if queue_size > 0:
        message += f"📬 待处理事件: {queue_size}\n"

    # 最后执行时间
    last_exec = status.get('last_workflow_execution')
    if last_exec:
        message += f"\n⏰ 上次执行: {last_exec}"

    return message


def format_orders_message(orders: List[Any]) -> str:
    """
    格式化订单列表消息

    Args:
        orders: 订单列表

    Returns:
        格式化的消息字符串
    """
    if not orders:
        return "📝 **活跃订单**\n\n_暂无活跃订单_"

    message = f"📝 **活跃订单 ({len(orders)})**\n\n"

    for order in orders[:10]:
        symbol = getattr(order, 'symbol', 'N/A')
        side = getattr(order, 'side', 'N/A')
        if hasattr(side, 'value'):
            side = side.value
        qty = getattr(order, 'quantity', 0)
        status = getattr(order, 'status', 'N/A')
        if hasattr(status, 'value'):
            status = status.value

        side_emoji = "🟢" if 'buy' in str(side).lower() else "🔴"
        message += f"{side_emoji} `{symbol}` {side} {qty} - {status}\n"

    if len(orders) > 10:
        message += f"\n_... 还有 {len(orders) - 10} 个订单_"

    return message


def format_trade_result(result: Dict[str, Any]) -> str:
    """
    格式化交易结果消息

    Args:
        result: 交易结果字典

    Returns:
        格式化的消息字符串
    """
    success = result.get('success', False)
    emoji = "✅" if success else "❌"

    message = f"{emoji} **交易结果**\n\n"

    if 'trades' in result:
        trades = result['trades']
        success_count = sum(1 for t in trades if t.get('success'))
        message += f"• 总交易: {len(trades)}\n"
        message += f"• 成功: {success_count}\n"
        message += f"• 失败: {len(trades) - success_count}\n"

    if 'error' in result and result['error']:
        message += f"\n⚠️ 错误: {result['error']}"

    return message


def format_workflow_result(result: Dict[str, Any]) -> str:
    """
    格式化工作流执行结果

    Args:
        result: 工作流结果字典

    Returns:
        格式化的消息字符串
    """
    success = result.get('success', False)
    emoji = "🎯" if success else "❌"

    message = f"{emoji} **工作流执行完成**\n\n"

    workflow_type = result.get('workflow_type', 'N/A')
    trigger = result.get('trigger', 'N/A')
    execution_time = result.get('execution_time', 0)

    message += f"• 类型: {workflow_type}\n"
    message += f"• 触发: {trigger}\n"
    message += f"• 耗时: {execution_time:.1f}s\n"

    if 'llm_response' in result and result['llm_response']:
        # 截断过长的 LLM 响应
        response = result['llm_response']
        if len(response) > 500:
            response = response[:500] + "..."
        message += f"\n💬 **AI 分析**\n{response}"

    return message


def format_workflow_message(
    workflow_type: str,
    message: str,
    data: Dict[str, Any] = None
) -> str:
    """
    格式化工作流通知消息

    Args:
        workflow_type: 工作流类型
        message: 通知消息
        data: 附加数据
    """
    emoji_map = {
        'analysis': '🔍',
        'rebalance': '⚖️',
        'risk_check': '🛡️',
        'portfolio_check': '📊',
        'daily': '📅'
    }
    emoji = emoji_map.get(workflow_type.lower(), '📋')

    result = f"{emoji} **工作流: {workflow_type}**\n\n{message}"

    if data:
        result += "\n\n**详情:**\n"
        for key, value in data.items():
            result += f"• {key}: {value}\n"

    return result


def format_trade_execution_message(
    symbol: str,
    action: str,
    quantity: str,
    order_id: str
) -> str:
    """
    格式化交易执行消息

    Args:
        symbol: 股票代码
        action: 交易动作 (BUY/SELL)
        quantity: 数量
        order_id: 订单 ID
    """
    emoji = "🟢" if action.upper() == "BUY" else "🔴"
    action_text = "买入" if action.upper() == "BUY" else "卖出"

    return f"""{emoji} **交易执行**

• 股票: `{symbol}`
• 操作: {action_text}
• 数量: {quantity}
• 订单ID: `{order_id[:8]}...`
"""


def format_tool_result_message(
    tool_name: str,
    tool_args: dict,
    tool_result: str,
    success: bool = True
) -> str:
    """
    格式化工具执行结果消息

    Args:
        tool_name: 工具名称
        tool_args: 工具参数
        tool_result: 执行结果
        success: 是否成功
    """
    emoji = "✅" if success else "❌"
    status = "成功" if success else "失败"

    # 截断过长的结果
    result_display = tool_result
    if len(result_display) > 300:
        result_display = result_display[:300] + "..."

    # 格式化参数
    args_display = ", ".join(f"{k}={v}" for k, v in tool_args.items())
    if len(args_display) > 100:
        args_display = args_display[:100] + "..."

    return f"""{emoji} **工具执行{status}**

🔧 工具: `{tool_name}`
📝 参数: `{args_display}`
📤 结果: {result_display}
"""


def format_analysis_summary_message(analysis_text: str) -> str:
    """
    格式化分析摘要消息

    Args:
        analysis_text: 分析文本
    """
    # 截断过长的分析
    if len(analysis_text) > 2000:
        analysis_text = analysis_text[:2000] + "\n\n... (内容已截断)"

    return f"""🔍 **AI 分析摘要**

{analysis_text}
"""


def format_decision_summary_message(decision) -> str:
    """
    格式化决策摘要消息

    Args:
        decision: TradingDecision 对象或 None
    """
    if decision is None:
        return "📊 **交易决策**\n\n_暂无交易决策_"

    action = getattr(decision, 'action', 'HOLD')
    symbol = getattr(decision, 'symbol', 'N/A')
    confidence = getattr(decision, 'confidence', 0)
    reasoning = getattr(decision, 'reasoning', '')

    action_emoji = {
        'BUY': '🟢',
        'SELL': '🔴',
        'HOLD': '⏸️'
    }.get(str(action).upper(), '📊')

    message = f"""{action_emoji} **交易决策**

• 操作: {action}
• 股票: `{symbol}`
• 置信度: {confidence:.0%}
"""

    if reasoning:
        if len(reasoning) > 500:
            reasoning = reasoning[:500] + "..."
        message += f"\n💭 **分析理由:**\n{reasoning}"

    return message


def format_reasoning_summary_message(
    reasoning_text: str,
    tool_calls_count: int = 0
) -> str:
    """
    格式化 AI 推理摘要消息

    Args:
        reasoning_text: AI 推理文本
        tool_calls_count: 工具调用次数
    """
    if len(reasoning_text) > 1500:
        reasoning_text = reasoning_text[:1500] + "\n\n... (内容已截断)"

    message = f"""🧠 **AI 分析推理**

{reasoning_text}
"""

    if tool_calls_count > 0:
        message += f"\n📊 工具调用次数: {tool_calls_count}"

    return message


def _get_event_text(event_type: str) -> str:
    """获取事件文本"""
    mapping = {
        'created': '已创建',
        'filled': '已成交',
        'cancelled': '已取消',
        'rejected': '已拒绝',
        'partial': '部分成交'
    }
    return mapping.get(event_type, event_type)
