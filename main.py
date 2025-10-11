import asyncio
import logging
import signal
import sys
from pathlib import Path
from datetime import datetime

from src.trading_system import TradingSystem
from src.interfaces.factory import get_news_api
from config import settings


# Setup logging
def setup_logging():
    """Setup logging configuration"""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    # Create formatters
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Setup file handler with UTF-8 encoding
    file_handler = logging.FileHandler(
        log_dir / f"trading_agent_{datetime.now().strftime('%Y%m%d')}.log",
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)
    
    # Setup console handler with UTF-8 encoding
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)
    
    # Force UTF-8 encoding for Windows
    if hasattr(console_handler.stream, 'reconfigure'):
        try:
            console_handler.stream.reconfigure(encoding='utf-8')
        except Exception:
            pass  # Fallback to default encoding
    
    # Setup root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, settings.log_level.upper()))
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    
    # Reduce noise from external libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)


async def main():
    """Main entry point for the trading system"""
    
    # Setup logging
    setup_logging()
    logger = logging.getLogger(__name__)
    
    # Create trading system
    trading_system = TradingSystem()
    
    # Setup graceful shutdown
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, shutting down...")
        asyncio.create_task(trading_system.stop())
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        logger.info("=" * 50)
        logger.info("🚀 Starting LLM Trading Agent")
        logger.info("=" * 50)
        
        # Print system info
        logger.info(f"Environment: {settings.environment}")
        logger.info(f"Alpaca Base URL: {settings.alpaca_base_url}")
        logger.info(f"LLM Provider: {settings.llm_provider}")
        if settings.llm_provider.lower() == "openai":
            logger.info(f"OpenAI Model: {settings.openai_model}")
        elif settings.llm_provider.lower() == "deepseek":
            logger.info(f"DeepSeek Model: {settings.deepseek_model}")
        
        # Display news provider information
        try:
            news_api = get_news_api()
            news_info = news_api.get_provider_info()
            logger.info(f"News Provider: {news_info['name']} ({news_info['configured'] and 'configured' or 'not configured'})")
        except Exception as e:
            logger.warning(f"Failed to get news provider info: {e}")
        
        logger.info(f"Rebalance Time: {settings.rebalance_time}")
        logger.info(f"Stop Loss: {settings.stop_loss_percentage}%")
        logger.info(f"Take Profit: {settings.take_profit_percentage}%")
        
        # Start the trading system
        await trading_system.start()
        
        logger.info("🎯 Trading system started successfully!")
        logger.info("📱 Telegram bot is ready for commands")
        logger.info("📊 Daily rebalancing scheduled")
        logger.info("⚡ Event-driven system active")
        
        # Keep the main loop running
        while True:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received, shutting down...")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise
    finally:
        # Cleanup
        await trading_system.stop()
        logger.info("🛑 Trading system stopped")


if __name__ == "__main__":
    """Run the trading system"""
    
    print("""
    ╔════════════════════════════════════════════════════════════════╗
    ║                                                                ║
    ║                    🤖 LLM Trading Agent                        ║
    ║                                                                ║
    ║   Powered by OpenAI/DeepSeek • Alpaca API • Tiingo           ║
    ║                                                                ║
    ║                     Built with LangGraph                       ║
    ║                                                                ║
    ╚════════════════════════════════════════════════════════════════╝
    """)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        sys.exit(1) 