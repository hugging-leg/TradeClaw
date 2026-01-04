"""
查询命令

处理 /status, /portfolio, /orders 等查询命令
"""

from src.utils.logging_config import get_logger
from typing import Dict, Callable

from telegram import Update
from telegram.ext import ContextTypes

from .base import CommandHandler, CommandContext

logger = get_logger(__name__)


class QueryCommands(CommandHandler):
    """查询命令处理器"""
    
    def get_commands(self) -> Dict[str, str]:
        return {
            'status': '获取系统状态',
            'portfolio': '获取投资组合',
            'orders': '获取活跃订单',
            'help': '显示帮助信息'
        }
    
    def get_handlers(self) -> Dict[str, Callable]:
        return {
            'status': self.handle_status,
            'portfolio': self.handle_portfolio,
            'orders': self.handle_orders,
            'help': self.handle_help
        }
    
    async def handle_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理 /status - 获取系统状态"""
        ctx = CommandContext.from_update(update)
        
        if not self.is_authorized(ctx):
            await update.message.reply_text("❌ 未授权访问")
            return
        
        try:
            await self.publish_event("query_status", {"chat_id": ctx.chat_id})
            logger.debug(f"用户 {ctx.username or ctx.user_id} 查询系统状态")
        except Exception as e:
            logger.error(f"查询状态失败: {e}")
            await update.message.reply_text("❌ 获取状态失败")
    
    async def handle_portfolio(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理 /portfolio - 获取投资组合"""
        ctx = CommandContext.from_update(update)
        
        if not self.is_authorized(ctx):
            await update.message.reply_text("❌ 未授权访问")
            return
        
        try:
            await self.publish_event("query_portfolio", {"chat_id": ctx.chat_id})
            logger.debug(f"用户 {ctx.username or ctx.user_id} 查询投资组合")
        except Exception as e:
            logger.error(f"查询投资组合失败: {e}")
            await update.message.reply_text("❌ 获取投资组合失败")
    
    async def handle_orders(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理 /orders - 获取活跃订单"""
        ctx = CommandContext.from_update(update)
        
        if not self.is_authorized(ctx):
            await update.message.reply_text("❌ 未授权访问")
            return
        
        try:
            await self.publish_event("query_orders", {"chat_id": ctx.chat_id})
            logger.debug(f"用户 {ctx.username or ctx.user_id} 查询订单")
        except Exception as e:
            logger.error(f"查询订单失败: {e}")
            await update.message.reply_text("❌ 获取订单失败")
    
    async def handle_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理 /help - 显示帮助"""
        ctx = CommandContext.from_update(update)
        
        if not self.is_authorized(ctx):
            await update.message.reply_text("❌ 未授权访问")
            return
        
        # 帮助信息直接在此返回，不需要通过事件系统
        help_text = """🤖 **LLM Trading Agent 命令**

**交易控制：**
/start - 启用交易
/stop - 暂停交易
/emergency - 紧急停止

**查询信息：**
/status - 系统状态
/portfolio - 投资组合
/orders - 活跃订单

**分析操作：**
/analyze - 手动触发 AI 分析

💡 使用 /status 可以快速查看当前系统状态
"""
        await update.message.reply_text(help_text, parse_mode='Markdown')

