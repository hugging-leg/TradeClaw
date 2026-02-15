import asyncio
import logging
import signal
import sys
from pathlib import Path

from src.trading_system import TradingSystem
from src.interfaces.factory import get_news_api
from src.utils.logging_config import setup_logging as setup_structlog, get_logger
from config import settings


async def main():
    """Main entry point for the trading system"""

    # Setup structured logging
    setup_structlog()
    logger = get_logger(__name__)

    # Create trading system
    trading_system = TradingSystem()

    # Graceful shutdown flag
    shutdown_event = asyncio.Event()

    # Setup graceful shutdown using loop.add_signal_handler
    loop = asyncio.get_running_loop()

    def signal_handler():
        logger.info("Received shutdown signal, initiating graceful shutdown...")
        shutdown_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler for SIGTERM
            signal.signal(sig, lambda s, f: signal_handler())

    try:
        logger.info("=" * 50)
        logger.info("🚀 Starting LLM Trading Agent")
        logger.info("=" * 50)

        # Print system info
        logger.info(f"Environment: {settings.environment}")
        logger.info(f"Data Dir: {settings.get_data_dir()}")
        logger.info(f"Database: {settings.get_database_url().split('@')[-1] if '@' in settings.get_database_url() else settings.get_database_url()}")
        logger.info(f"Timezone: {settings.trading_timezone}")
        logger.info(f"Exchange: {settings.exchange}")
        logger.info(f"Broker: {settings.broker_provider}")
        logger.info(f"LLM: {settings.llm_model} @ {settings.llm_base_url}")

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
        logger.info("📊 Daily rebalancing scheduled (APScheduler)")
        logger.info("⚡ Event-driven system active")

        # Wait for shutdown signal (replaces busy-wait `while True: sleep(1)`)
        await shutdown_event.wait()
        logger.info("Shutdown signal received, stopping...")

    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise
    finally:
        # Cleanup — only called once
        await trading_system.stop()
        logger.info("🛑 Trading system stopped")


if __name__ == "__main__":
    """Run the trading system"""

    print("""
    ╔════════════════════════════════════════════════════════════════╗
    ║                                                                ║
    ║                    🤖 LLM Trading Agent                        ║
    ║                                                                ║
    ║   Powered by OpenAI/DeepSeek • Alpaca API • Tiingo             ║
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
