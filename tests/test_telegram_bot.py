"""
Unit tests for Telegram bot API.
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from decimal import Decimal
from datetime import datetime, timezone
from src.apis.telegram_bot import TelegramBot
from src.models.trading_models import Order, OrderSide, OrderType, Portfolio, Position, PositionSide
from config import Settings


class TestTelegramBot:
    """Test TelegramBot class."""
    
    @pytest.fixture
    def mock_settings(self):
        """Create mock settings."""
        settings = Mock(spec=Settings)
        settings.telegram_bot_token = "test_bot_token"
        settings.telegram_chat_id = "test_chat_id"
        return settings
    
    @pytest.fixture
    def telegram_bot(self, mock_settings):
        """Create TelegramBot instance with mocked dependencies."""
        with patch('src.apis.telegram_bot.settings', mock_settings):
            with patch('telegram.Bot') as mock_bot:
                with patch('telegram.ext.Application') as mock_app:
                    bot = TelegramBot()
                    bot.bot = mock_bot.return_value
                    bot.application = mock_app.return_value
                    return bot
    
    @pytest.fixture
    def mock_update(self):
        """Create a mock Telegram update."""
        update = Mock()
        update.effective_chat.id = "test_chat_id"
        update.message.text = "/start"
        return update
    
    @pytest.fixture
    def mock_context(self):
        """Create a mock Telegram context."""
        context = Mock()
        context.bot = Mock()
        context.bot.send_message = AsyncMock()
        return context
    
    def test_telegram_bot_initialization(self, telegram_bot):
        """Test TelegramBot initialization."""
        assert telegram_bot.bot is not None
        assert telegram_bot.application is not None
        assert telegram_bot.chat_id == "test_chat_id"
        assert telegram_bot.is_running is False
    
    @pytest.mark.asyncio
    async def test_send_message(self, telegram_bot):
        """Test sending a message."""
        telegram_bot.bot.send_message = AsyncMock()
        
        await telegram_bot.send_message("Test message")
        
        telegram_bot.bot.send_message.assert_called_once_with(
            chat_id="test_chat_id",
            text="Test message",
            parse_mode="HTML"
        )
    
    @pytest.mark.asyncio
    async def test_send_message_with_custom_chat_id(self, telegram_bot):
        """Test sending a message to a specific chat."""
        telegram_bot.bot.send_message = AsyncMock()
        
        await telegram_bot.send_message("Test message", chat_id="custom_chat_id")
        
        telegram_bot.bot.send_message.assert_called_once_with(
            chat_id="custom_chat_id",
            text="Test message",
            parse_mode="HTML"
        )
    
    @pytest.mark.asyncio
    async def test_send_message_error_handling(self, telegram_bot):
        """Test error handling in send_message."""
        telegram_bot.bot.send_message = AsyncMock(side_effect=Exception("API error"))
        
        # Should not raise an exception
        await telegram_bot.send_message("Test message")
    
    @pytest.mark.asyncio
    async def test_send_order_notification(self, telegram_bot):
        """Test sending order notification."""
        order = Order(
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("100"),
            id="order_123"
        )
        
        telegram_bot.bot.send_message = AsyncMock()
        
        await telegram_bot.send_order_notification(order, "created")
        
        telegram_bot.bot.send_message.assert_called_once()
        call_args = telegram_bot.bot.send_message.call_args
        message_text = call_args[1]['text']
        
        assert "Order Created" in message_text
        assert "AAPL" in message_text
        assert "BUY" in message_text
        assert "100" in message_text
    
    @pytest.mark.asyncio
    async def test_send_filled_order_notification(self, telegram_bot):
        """Test sending filled order notification."""
        order = Order(
            symbol="TSLA",
            side=OrderSide.SELL,
            order_type=OrderType.LIMIT,
            quantity=Decimal("50"),
            price=Decimal("200.50"),
            filled_quantity=Decimal("50"),
            filled_price=Decimal("201.00"),
            id="order_456"
        )
        
        telegram_bot.bot.send_message = AsyncMock()
        
        await telegram_bot.send_order_notification(order, "filled")
        
        telegram_bot.bot.send_message.assert_called_once()
        call_args = telegram_bot.bot.send_message.call_args
        message_text = call_args[1]['text']
        
        assert "Order Filled" in message_text
        assert "TSLA" in message_text
        assert "SELL" in message_text
        assert "50" in message_text
        assert "201.00" in message_text
    
    @pytest.mark.asyncio
    async def test_send_portfolio_summary(self, telegram_bot):
        """Test sending portfolio summary."""
        positions = [
            Position(
                symbol="AAPL",
                quantity=Decimal("100"),
                market_value=Decimal("15000.00"),
                avg_entry_price=Decimal("150.00"),
                side=PositionSide.LONG,
                unrealized_pnl=Decimal("500.00")
            ),
            Position(
                symbol="GOOGL",
                quantity=Decimal("10"),
                market_value=Decimal("2500.00"),
                avg_entry_price=Decimal("2500.00"),
                side=PositionSide.LONG,
                unrealized_pnl=Decimal("0.00")
            )
        ]
        
        portfolio = Portfolio(
            equity=Decimal("25000.00"),
            cash=Decimal("7500.00"),
            market_value=Decimal("17500.00"),
            day_pnl=Decimal("500.00"),
            total_pnl=Decimal("2500.00"),
            positions=positions
        )
        
        telegram_bot.bot.send_message = AsyncMock()
        
        await telegram_bot.send_portfolio_summary(portfolio)
        
        telegram_bot.bot.send_message.assert_called_once()
        call_args = telegram_bot.bot.send_message.call_args
        message_text = call_args[1]['text']
        
        assert "Portfolio Summary" in message_text
        assert "25000.00" in message_text
        assert "AAPL" in message_text
        assert "GOOGL" in message_text
    
    @pytest.mark.asyncio
    async def test_send_system_alert(self, telegram_bot):
        """Test sending system alert."""
        telegram_bot.bot.send_message = AsyncMock()
        
        await telegram_bot.send_system_alert("Risk limit exceeded", "warning")
        
        telegram_bot.bot.send_message.assert_called_once()
        call_args = telegram_bot.bot.send_message.call_args
        message_text = call_args[1]['text']
        
        assert "⚠️ WARNING" in message_text
        assert "Risk limit exceeded" in message_text
    
    @pytest.mark.asyncio
    async def test_send_system_alert_error(self, telegram_bot):
        """Test sending error system alert."""
        telegram_bot.bot.send_message = AsyncMock()
        
        await telegram_bot.send_system_alert("System error occurred", "error")
        
        telegram_bot.bot.send_message.assert_called_once()
        call_args = telegram_bot.bot.send_message.call_args
        message_text = call_args[1]['text']
        
        assert "🚨 ERROR" in message_text
        assert "System error occurred" in message_text
    
    @pytest.mark.asyncio
    async def test_start_command(self, telegram_bot, mock_update, mock_context):
        """Test /start command handler."""
        await telegram_bot.start_command(mock_update, mock_context)
        
        mock_context.bot.send_message.assert_called_once()
        call_args = mock_context.bot.send_message.call_args
        message_text = call_args[1]['text']
        
        assert "Trading Agent Bot" in message_text
        assert "/help" in message_text
    
    @pytest.mark.asyncio
    async def test_help_command(self, telegram_bot, mock_update, mock_context):
        """Test /help command handler."""
        await telegram_bot.help_command(mock_update, mock_context)
        
        mock_context.bot.send_message.assert_called_once()
        call_args = mock_context.bot.send_message.call_args
        message_text = call_args[1]['text']
        
        assert "Available Commands" in message_text
        assert "/status" in message_text
        assert "/portfolio" in message_text
    
    @pytest.mark.asyncio
    async def test_status_command(self, telegram_bot, mock_update, mock_context):
        """Test /status command handler."""
        # Mock the trading system
        mock_trading_system = Mock()
        mock_trading_system.is_running = True
        mock_trading_system.get_system_status = AsyncMock(return_value={
            "market_open": True,
            "last_rebalance": "2023-10-30 09:30:00",
            "active_orders": 2,
            "positions": 3
        })
        
        telegram_bot.trading_system = mock_trading_system
        
        await telegram_bot.status_command(mock_update, mock_context)
        
        mock_context.bot.send_message.assert_called_once()
        call_args = mock_context.bot.send_message.call_args
        message_text = call_args[1]['text']
        
        assert "System Status" in message_text
        assert "Running" in message_text
    
    @pytest.mark.asyncio
    async def test_status_command_no_trading_system(self, telegram_bot, mock_update, mock_context):
        """Test /status command when trading system is not available."""
        telegram_bot.trading_system = None
        
        await telegram_bot.status_command(mock_update, mock_context)
        
        mock_context.bot.send_message.assert_called_once()
        call_args = mock_context.bot.send_message.call_args
        message_text = call_args[1]['text']
        
        assert "not available" in message_text
    
    @pytest.mark.asyncio
    async def test_portfolio_command(self, telegram_bot, mock_update, mock_context):
        """Test /portfolio command handler."""
        # Mock the trading system
        mock_trading_system = Mock()
        mock_portfolio = Portfolio(
            equity=Decimal("25000.00"),
            cash=Decimal("7500.00"),
            market_value=Decimal("17500.00"),
            day_pnl=Decimal("500.00"),
            total_pnl=Decimal("2500.00"),
            positions=[]
        )
        mock_trading_system.get_portfolio = AsyncMock(return_value=mock_portfolio)
        
        telegram_bot.trading_system = mock_trading_system
        
        await telegram_bot.portfolio_command(mock_update, mock_context)
        
        mock_context.bot.send_message.assert_called_once()
        call_args = mock_context.bot.send_message.call_args
        message_text = call_args[1]['text']
        
        assert "Portfolio" in message_text
        assert "25000.00" in message_text
    
    @pytest.mark.asyncio
    async def test_orders_command(self, telegram_bot, mock_update, mock_context):
        """Test /orders command handler."""
        # Mock the trading system
        mock_trading_system = Mock()
        mock_orders = [
            Order(
                symbol="AAPL",
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=Decimal("100"),
                id="order_123"
            )
        ]
        mock_trading_system.get_orders = AsyncMock(return_value=mock_orders)
        
        telegram_bot.trading_system = mock_trading_system
        
        await telegram_bot.orders_command(mock_update, mock_context)
        
        mock_context.bot.send_message.assert_called_once()
        call_args = mock_context.bot.send_message.call_args
        message_text = call_args[1]['text']
        
        assert "Active Orders" in message_text
        assert "AAPL" in message_text
    
    @pytest.mark.asyncio
    async def test_emergency_stop_command(self, telegram_bot, mock_update, mock_context):
        """Test /emergency_stop command handler."""
        # Mock the trading system
        mock_trading_system = Mock()
        mock_trading_system.emergency_stop = AsyncMock()
        
        telegram_bot.trading_system = mock_trading_system
        
        await telegram_bot.emergency_stop_command(mock_update, mock_context)
        
        mock_trading_system.emergency_stop.assert_called_once()
        mock_context.bot.send_message.assert_called_once()
        call_args = mock_context.bot.send_message.call_args
        message_text = call_args[1]['text']
        
        assert "Emergency stop" in message_text
    
    @pytest.mark.asyncio
    async def test_stop_trading_command(self, telegram_bot, mock_update, mock_context):
        """Test /stop command handler."""
        # Mock the trading system
        mock_trading_system = Mock()
        mock_trading_system.stop_trading = AsyncMock()
        
        telegram_bot.trading_system = mock_trading_system
        
        await telegram_bot.stop_trading_command(mock_update, mock_context)
        
        mock_trading_system.stop_trading.assert_called_once()
        mock_context.bot.send_message.assert_called_once()
        call_args = mock_context.bot.send_message.call_args
        message_text = call_args[1]['text']
        
        assert "Trading stopped" in message_text
    
    @pytest.mark.asyncio
    async def test_start_trading_command(self, telegram_bot, mock_update, mock_context):
        """Test /start_trading command handler."""
        # Mock the trading system
        mock_trading_system = Mock()
        mock_trading_system.start_trading = AsyncMock()
        
        telegram_bot.trading_system = mock_trading_system
        
        await telegram_bot.start_trading_command(mock_update, mock_context)
        
        mock_trading_system.start_trading.assert_called_once()
        mock_context.bot.send_message.assert_called_once()
        call_args = mock_context.bot.send_message.call_args
        message_text = call_args[1]['text']
        
        assert "Trading started" in message_text
    
    @pytest.mark.asyncio
    async def test_unauthorized_access(self, telegram_bot, mock_update, mock_context):
        """Test unauthorized access to commands."""
        # Mock update from unauthorized user
        mock_update.effective_chat.id = "unauthorized_chat_id"
        
        await telegram_bot.start_command(mock_update, mock_context)
        
        mock_context.bot.send_message.assert_called_once()
        call_args = mock_context.bot.send_message.call_args
        message_text = call_args[1]['text']
        
        assert "Unauthorized access" in message_text
    
    @pytest.mark.asyncio
    async def test_start_bot(self, telegram_bot):
        """Test starting the bot."""
        telegram_bot.application.run_polling = AsyncMock()
        
        await telegram_bot.start()
        
        assert telegram_bot.is_running is True
        # Note: run_polling is typically called in a separate task
    
    @pytest.mark.asyncio
    async def test_stop_bot(self, telegram_bot):
        """Test stopping the bot."""
        telegram_bot.application.stop = AsyncMock()
        telegram_bot.application.shutdown = AsyncMock()
        telegram_bot.is_running = True
        
        await telegram_bot.stop()
        
        assert telegram_bot.is_running is False
        telegram_bot.application.stop.assert_called_once()
        telegram_bot.application.shutdown.assert_called_once()
    
    def test_format_currency(self, telegram_bot):
        """Test currency formatting."""
        formatted = telegram_bot._format_currency(Decimal("1234.56"))
        assert formatted == "$1,234.56"
        
        formatted = telegram_bot._format_currency(Decimal("-1234.56"))
        assert formatted == "-$1,234.56"
    
    def test_format_percentage(self, telegram_bot):
        """Test percentage formatting."""
        formatted = telegram_bot._format_percentage(Decimal("0.0523"))
        assert formatted == "5.23%"
        
        formatted = telegram_bot._format_percentage(Decimal("-0.0523"))
        assert formatted == "-5.23%"
    
    def test_get_status_emoji(self, telegram_bot):
        """Test status emoji selection."""
        assert telegram_bot._get_status_emoji("info") == "ℹ️"
        assert telegram_bot._get_status_emoji("warning") == "⚠️"
        assert telegram_bot._get_status_emoji("error") == "🚨"
        assert telegram_bot._get_status_emoji("success") == "✅"
        assert telegram_bot._get_status_emoji("unknown") == "ℹ️"


class TestTelegramBotIntegration:
    """Integration tests for Telegram bot."""
    
    @pytest.mark.asyncio
    async def test_command_registration(self):
        """Test that all commands are properly registered."""
        with patch('src.apis.telegram_bot.settings') as mock_settings:
            mock_settings.telegram_bot_token = "test_token"
            mock_settings.telegram_chat_id = "test_chat_id"
            
            with patch('telegram.Bot') as mock_bot:
                with patch('telegram.ext.Application') as mock_app:
                    mock_application = Mock()
                    mock_app.return_value = mock_application
                    
                    bot = TelegramBot()
                    
                    # Verify that add_handler was called for each command
                    expected_commands = [
                        "start", "help", "status", "portfolio", "orders",
                        "emergency_stop", "stop", "start_trading"
                    ]
                    
                    # Check that handlers were added
                    assert mock_application.add_handler.call_count >= len(expected_commands)
    
    @pytest.mark.asyncio
    async def test_end_to_end_notification_flow(self):
        """Test complete notification flow."""
        with patch('src.apis.telegram_bot.settings') as mock_settings:
            mock_settings.telegram_bot_token = "test_token"
            mock_settings.telegram_chat_id = "test_chat_id"
            
            with patch('telegram.Bot') as mock_bot:
                with patch('telegram.ext.Application') as mock_app:
                    mock_bot_instance = Mock()
                    mock_bot_instance.send_message = AsyncMock()
                    mock_bot.return_value = mock_bot_instance
                    
                    bot = TelegramBot()
                    
                    # Test order notification
                    order = Order(
                        symbol="AAPL",
                        side=OrderSide.BUY,
                        order_type=OrderType.MARKET,
                        quantity=Decimal("100"),
                        id="order_123"
                    )
                    
                    await bot.send_order_notification(order, "created")
                    
                    # Verify message was sent
                    mock_bot_instance.send_message.assert_called_once()
                    
                    # Test system alert
                    await bot.send_system_alert("Test alert", "info")
                    
                    # Verify second message was sent
                    assert mock_bot_instance.send_message.call_count == 2


@pytest.mark.integration
class TestTelegramBotRealIntegration:
    """Integration tests with real Telegram API (requires real credentials)."""
    
    @pytest.mark.skip(reason="Requires real Telegram credentials")
    @pytest.mark.asyncio
    async def test_real_telegram_connection(self):
        """Test connecting to real Telegram API."""
        # This test would require real credentials and would be run separately
        # in an integration test environment
        pass
    
    @pytest.mark.skip(reason="Requires real Telegram credentials")
    @pytest.mark.asyncio
    async def test_real_message_sending(self):
        """Test sending real messages."""
        # This test would require real credentials and would be run separately
        # in an integration test environment
        pass 