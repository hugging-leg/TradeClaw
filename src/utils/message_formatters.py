"""
Message formatting utilities for the trading system.

This module contains functions for formatting various types of trading system messages
with consistent styling and emoji usage.
"""

from datetime import datetime
from typing import Dict, Any, Optional
from decimal import Decimal

from .string_utils import format_currency, format_percentage
from .telegram_utils import escape_markdown_symbols


def format_alert_message(message: str, alert_type: str) -> str:
    """
    Format system alert message.
    
    Args:
        message: Alert message content
        alert_type: Type of alert (info, warning, error, success)
        
    Returns:
        Formatted alert message
    """
    emoji_map = {
        'info': 'ℹ️',
        'warning': '⚠️',
        'error': '🚨',
        'success': '✅'
    }
    
    emoji = emoji_map.get(alert_type, 'ℹ️')
    title = alert_type.upper()
    
    formatted_message = f"""
{emoji} *{title}*

{message}

📅 *Time*: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    """
    
    return formatted_message.strip()


def format_portfolio_message(portfolio) -> str:
    """
    Format portfolio update message.
    
    Args:
        portfolio: Portfolio object with equity, pnl, positions, etc.
        
    Returns:
        Formatted portfolio message
    """
    try:
        day_pnl = float(portfolio.day_pnl)
        equity = float(portfolio.equity)
        day_pnl_pct = (day_pnl / equity) * 100 if equity != 0 else 0
    except (ValueError, TypeError, AttributeError):
        day_pnl_pct = 0
    
    pnl_emoji = "📈" if day_pnl > 0 else "📉" if day_pnl < 0 else "➡️"
    
    try:
        message = f"""
💼 *Portfolio Update*

💰 *Total Equity*: {format_currency(portfolio.equity)}
{pnl_emoji} *Day P&L*: {format_currency(portfolio.day_pnl)} ({day_pnl_pct:.2f}%)
📊 *Market Value*: {format_currency(portfolio.market_value)}
💵 *Cash*: {format_currency(portfolio.cash)}
📈 *Total P&L*: {format_currency(portfolio.total_pnl)}

📦 *Positions*: {len(portfolio.positions)}
        """
    except AttributeError as e:
        # Fallback if portfolio object doesn't have expected attributes
        message = f"""
💼 *Portfolio Update*

Portfolio information temporarily unavailable.

📅 *Time*: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """
    
    return message.strip()


def format_order_message(order, event_type: str) -> str:
    """
    Format order notification message.
    
    Args:
        order: Order object
        event_type: Type of order event (created, filled, canceled, etc.)
        
    Returns:
        Formatted order message
    """
    emoji_map = {
        'created': '📝',
        'filled': '✅',
        'partially_filled': '📊',
        'canceled': '❌',
        'rejected': '🚫'
    }
    
    emoji = emoji_map.get(event_type, '📝')
    title = f"Order {event_type.replace('_', ' ').title()}"
    
    try:
        # Escape symbol to prevent markdown issues
        safe_symbol = escape_markdown_symbols(str(order.symbol))
        
        message = f"""
{emoji} *{title}*

📊 *Symbol*: {safe_symbol}
📈 *Side*: {order.side.value.upper()}
📦 *Quantity*: {order.quantity}
💰 *Type*: {order.order_type.value.upper()}
"""
        
        if hasattr(order, 'price') and order.price:
            message += f"💵 *Price*: {format_currency(order.price)}\n"
        
        if hasattr(order, 'filled_quantity') and order.filled_quantity and order.filled_quantity > 0:
            message += f"✅ *Filled*: {order.filled_quantity}\n"
        
        if hasattr(order, 'filled_price') and order.filled_price:
            message += f"💲 *Fill Price*: {format_currency(order.filled_price)}\n"
        
        if hasattr(order, 'id') and order.id:
            message += f"🔢 *Order ID*: {order.id}\n"
            
    except AttributeError as e:
        message = f"""
{emoji} *{title}*

Order information temporarily unavailable.

📅 *Time*: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """
    
    return message.strip()


def format_workflow_message(workflow_type: str, message: str, data: Optional[Dict[str, Any]] = None) -> str:
    """
    Format workflow notification message.
    
    Args:
        workflow_type: Type of workflow (analysis, rebalance, etc.)
        message: Workflow message
        data: Additional data context
        
    Returns:
        Formatted workflow message
    """
    emoji_map = {
        'analysis': '📊',
        'rebalance': '⚖️',
        'risk_check': '🛡️',
        'eod_analysis': '🌅',
        'news_analysis': '📰',
        'manual_analysis': '🤖',
        'daily_rebalance': '⚖️'
    }
    
    emoji = emoji_map.get(workflow_type, '🔄')
    title = workflow_type.replace('_', ' ').title()
    
    formatted_message = f"""
{emoji} *{title}*

{message}
    """
    
    if data:
        formatted_message += "\n\n📋 *Details:*\n"
        for key, value in data.items():
            # Format key nicely
            formatted_key = key.replace('_', ' ').title()
            formatted_message += f"• {formatted_key}: {str(value)}\n"
    
    formatted_message += f"\n📅 *Time*: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    
    return formatted_message.strip()


def format_trade_execution_message(symbol: str, action: str, quantity: str, order_id: str) -> str:
    """
    Format trade execution notification.
    
    Args:
        symbol: Trading symbol
        action: Trade action (BUY/SELL)
        quantity: Quantity traded
        order_id: Order identifier
        
    Returns:
        Formatted trade execution message
    """
    # Escape symbol to prevent markdown issues
    safe_symbol = escape_markdown_symbols(str(symbol))
    
    execution_message = f"""
📈 *Trade Executed*

*Symbol*: {safe_symbol}
*Action*: {action.upper()}
*Quantity*: {quantity}
*Order ID*: {order_id}

📅 *Time*: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    """
    
    return execution_message.strip()


def format_tool_result_message(tool_name: str, tool_args: dict, tool_result: str, success: bool = True) -> str:
    """
    Format tool execution result message.
    
    Args:
        tool_name: Name of the executed tool
        tool_args: Arguments passed to the tool
        tool_result: Result returned by the tool
        success: Whether the tool execution was successful
        
    Returns:
        Formatted tool result message
    """
    status_emoji = "✅" if success else "❌"
    status_text = "Success" if success else "Failed"
    
    # Simple formatting - no complex escaping
    args_str = ""
    if tool_args:
        args_str = "\n*Arguments:*\n"
        for key, value in tool_args.items():
            # Limit argument value length and escape if needed
            arg_value = str(value)[:100]
            if len(str(value)) > 100:
                arg_value += "..."
            args_str += f"• {key}: {arg_value}\n"
    
    # Simple result preview
    result_preview = str(tool_result)[:500]
    if len(str(tool_result)) > 500:
        result_preview += "..."
    
    tool_message = f"""
🔧 *Tool Execution {status_text}*

*Tool*: {tool_name}
{args_str}
*Result:*
{result_preview}

📅 *Time*: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    """
    
    return tool_message.strip()


def format_analysis_summary_message(analysis_text: str, max_length: int = 1000) -> str:
    """
    Format analysis summary message.
    
    Args:
        analysis_text: Analysis summary text
        max_length: Maximum length for the analysis text
        
    Returns:
        Formatted analysis summary message
    """
    # Truncate analysis text if too long
    if len(analysis_text) > max_length:
        safe_analysis = analysis_text[:max_length - 3] + "..."
    else:
        safe_analysis = analysis_text
    
    summary_message = f"""
📊 *Analysis Summary*

{safe_analysis}

📅 *Time*: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    """
    
    return summary_message.strip()


def format_decision_summary_message(decision) -> str:
    """
    Format trading decision summary message.
    
    Args:
        decision: TradingDecision object or None
        
    Returns:
        Formatted decision summary message
    """
    if decision is None:
        decision_message = f"""
🤔 *Trading Decision*

*Action*: HOLD
*Reasoning*: No trading decision made

📅 *Time*: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """
    else:
        try:
            # Safe access to decision attributes
            action = getattr(decision, 'action', 'UNKNOWN')
            if hasattr(action, 'value'):
                action = action.value
            
            symbol = getattr(decision, 'symbol', 'N/A') or 'N/A'
            quantity = getattr(decision, 'quantity', 'N/A') or 'N/A'
            confidence = getattr(decision, 'confidence', 0.5)
            reasoning = getattr(decision, 'reasoning', 'No reasoning provided')
            
            # Escape symbol to prevent markdown issues
            safe_symbol = escape_markdown_symbols(str(symbol))
            
            # Truncate reasoning if too long
            if len(reasoning) > 400:
                safe_reasoning = reasoning[:397] + "..."
            else:
                safe_reasoning = reasoning
            
            decision_message = f"""
🎯 *Trading Decision*

*Action*: {str(action).upper()}
*Symbol*: {safe_symbol}
*Quantity*: {quantity}
*Confidence*: {float(confidence)*100:.1f}%

*Reasoning*: {safe_reasoning}

📅 *Time*: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            """
        except Exception as e:
            decision_message = f"""
🎯 *Trading Decision*

Decision information temporarily unavailable.

📅 *Time*: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            """
    
    return decision_message.strip()


def format_reasoning_summary_message(reasoning_text: str, tool_calls_count: int = 0) -> str:
    """
    Format AI reasoning summary message.
    
    Args:
        reasoning_text: The AI's reasoning and analysis
        tool_calls_count: Number of tools used in the analysis
        
    Returns:
        Formatted reasoning summary message
    """
    # Simple formatting with basic length limit
    safe_reasoning = str(reasoning_text)[:1000]
    if len(str(reasoning_text)) > 1000:
        safe_reasoning += "..."
    
    reasoning_message = f"""
🧠 *AI Reasoning & Analysis*

{safe_reasoning}

📊 *Tool Usage*: {tool_calls_count} tools executed
📅 *Time*: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    """
    
    return reasoning_message.strip()


def format_status_message(status_data: dict) -> str:
    """
    Format system status message.
    
    Args:
        status_data: Dictionary containing status information
        
    Returns:
        Formatted status message
    """
    try:
        status_text = f"""
📊 *Trading System Status*

🏃 *Running*: {("✅ Yes" if status_data.get('is_running') else "❌ No")}
💰 *Trading Enabled*: {("✅ Yes" if status_data.get('is_trading_enabled') else "❌ No")}
🏪 *Market Open*: {("✅ Yes" if status_data.get('is_market_open') else "❌ No")}

📈 *Portfolio Summary*:
• Total Equity: {format_currency(status_data.get('portfolio', {}).get('equity', 0))}
• Cash: {format_currency(status_data.get('portfolio', {}).get('cash', 0))}
• Day P&L: {format_currency(status_data.get('portfolio', {}).get('day_pnl', 0))}
• Positions: {len(status_data.get('portfolio', {}).get('positions', []))}

🕒 *Last Update*: {status_data.get('last_portfolio_update', 'N/A')}
        """
    except Exception as e:
        status_text = f"""
📊 *Trading System Status*

Status information temporarily unavailable.

📅 *Time*: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """
    
    return status_text.strip()


def format_portfolio_details_message(portfolio) -> str:
    """
    Format detailed portfolio message with positions.
    
    Args:
        portfolio: Portfolio object
        
    Returns:
        Formatted portfolio details message
    """
    try:
        portfolio_text = f"""
💼 *Portfolio Details*

💰 *Total Equity*: {format_currency(portfolio.equity)}
💵 *Cash*: {format_currency(portfolio.cash)}
📊 *Market Value*: {format_currency(portfolio.market_value)}
📈 *Day P&L*: {format_currency(portfolio.day_pnl)}
📊 *Total P&L*: {format_currency(portfolio.total_pnl)}

💪 *Buying Power*: {format_currency(portfolio.buying_power)}
📦 *Positions*: {len(portfolio.positions)}
        """
        
        if hasattr(portfolio, 'positions') and portfolio.positions:
            portfolio_text += "\n\n📋 *Current Positions:*\n"
            for position in portfolio.positions[:5]:  # Show first 5 positions
                # Escape underscores in symbol names to prevent markdown parsing issues
                safe_symbol = escape_markdown_symbols(str(position.symbol))
                portfolio_text += f"• {safe_symbol}: {position.quantity} shares\n"
            
            if len(portfolio.positions) > 5:
                portfolio_text += f"• ... and {len(portfolio.positions) - 5} more positions\n"
                
    except AttributeError as e:
        portfolio_text = f"""
💼 *Portfolio Details*

Portfolio information temporarily unavailable.

📅 *Time*: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """
    
    return portfolio_text.strip() 