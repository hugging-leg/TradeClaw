"""
分析命令

处理 /analyze 等分析相关命令
"""

from src.utils.logging_config import get_logger
from typing import Dict, Callable

from telegram import Update
from telegram.ext import ContextTypes

from .base import CommandHandler, CommandContext

logger = get_logger(__name__)


class AnalysisCommands(CommandHandler):
    """分析命令处理器"""
    
    def get_commands(self) -> Dict[str, str]:
        return {
            'analyze': '手动触发 AI 分析'
        }
    
    def get_handlers(self) -> Dict[str, Callable]:
        return {
            'analyze': self.handle_analyze
        }
    
    async def handle_analyze(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理 /analyze - 手动触发分析"""
        ctx = CommandContext.from_update(update)
        
        if not self.is_authorized(ctx):
            await update.message.reply_text("❌ 未授权访问")
            return
        
        try:
            # 先发送确认消息
            await update.message.reply_text(
                "🤖 **AI 分析已启动**\n\n正在执行智能交易分析...\n请稍候查看分析结果。",
                parse_mode='Markdown'
            )
            
            # 发布工作流触发事件
            await self.publish_event("trigger_workflow", {
                "trigger": "manual_analysis",
                "context": {
                    "source": "telegram",
                    "chat_id": ctx.chat_id,
                    "user": ctx.username or ctx.user_id
                }
            })
            
            logger.info(f"用户 {ctx.username or ctx.user_id} 触发了手动分析")
            
        except Exception as e:
            logger.error(f"触发分析失败: {e}")
            await update.message.reply_text("❌ 启动分析失败")

