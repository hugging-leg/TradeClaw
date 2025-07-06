"""
Unit tests for Telegram service.
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from decimal import Decimal
from datetime import datetime, timezone
from src.adapters.transports.telegram_service import TelegramService
from src.models.trading_models import Order, OrderSide, OrderType, Portfolio, Position, PositionSide
from config import Settings


class TestTelegramService:
    """Test TelegramService class."""
    
    @pytest.fixture
    def mock_settings(self):
        """Create mock settings."""
        settings = Mock(spec=Settings)
        settings.telegram_bot_token = "test_bot_token"
        settings.telegram_chat_id = "test_chat_id"
        return settings
    
    @pytest.fixture
    def mock_trading_system(self):
        """Create mock trading system."""
        trading_system = Mock()
        trading_system.get_status = AsyncMock(return_value={
            'status': 'running',
            'trading_enabled': True,
            'market_open': True,
            'equity': Decimal('100000.00'),
            'day_pnl': Decimal('500.00'),
            'active_orders': 2,
            'positions': 5,
            'last_update': '2023-01-01 12:00:00'
        })
        trading_system.get_portfolio = AsyncMock()
        trading_system.get_active_orders = AsyncMock(return_value=[])
        trading_system.start_trading = AsyncMock()
        trading_system.stop_trading = AsyncMock()
        trading_system.emergency_stop = AsyncMock()
        trading_system.is_running = True
        return trading_system
    
    @pytest.fixture
    def telegram_service(self, mock_settings, mock_trading_system):
        """Create TelegramService instance with mocked dependencies."""
        with patch('src.adapters.transports.telegram_service.settings', mock_settings):
            with patch('telegram.Bot') as mock_bot:
                with patch('telegram.ext.Application') as mock_app:
                    service = TelegramService(trading_system=mock_trading_system)
                    service.bot = mock_bot.return_value
                    service.application = mock_app.return_value
                    return service
    
    @pytest.fixture
    def mock_update(self):
        """Create a mock Telegram update."""
        update = Mock()
        update.effective_chat.id = "test_chat_id"
        update.message.text = "/start"
        update.message.reply_text = AsyncMock()
        return update
    
    @pytest.fixture
    def mock_context(self):
        """Create a mock Telegram context."""
        context = Mock()
        context.bot = Mock()
        context.bot.send_message = AsyncMock()
        return context
    
    def test_telegram_service_initialization(self, telegram_service):
        """Test TelegramService initialization."""
        assert telegram_service.bot_token == "test_bot_token"
        assert telegram_service.chat_id == "test_chat_id"
        assert telegram_service.trading_system is not None
        assert telegram_service.is_running is False
        assert len(telegram_service.commands) > 0
        assert telegram_service.get_transport_name() == "Telegram"
    
    @pytest.mark.asyncio
    async def test_initialize_success(self, telegram_service):
        """Test successful initialization."""
        with patch('telegram.Bot') as mock_bot:
            with patch('telegram.ext.Application') as mock_app:
                mock_bot.return_value.get_me = AsyncMock()
                mock_app.builder.return_value.token.return_value.build.return_value = mock_app.return_value
                
                result = await telegram_service.initialize()
                
                assert result is True
                assert telegram_service.bot is not None
                assert telegram_service.application is not None
    
    @pytest.mark.asyncio
    async def test_send_message(self, telegram_service):
        """Test sending a message via transport interface."""
        telegram_service.bot = Mock()
        telegram_service.bot.send_message = AsyncMock()
        
        result = await telegram_service.send_message("Test message")
        
        assert result is True
        telegram_service.bot.send_message.assert_called_once_with(
            chat_id="test_chat_id",
            text="Test message",
            parse_mode="Markdown"
        )
    
    @pytest.mark.asyncio
    async def test_start_command(self, telegram_service, mock_update, mock_context):
        """Test /start command handler."""
        telegram_service.trading_system.is_running = True
        
        await telegram_service._handle_start(mock_update, mock_context)
        
        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        message_text = call_args[0][0]
        
        assert "LLM Trading Agent Bot" in message_text
        assert "Welcome" in message_text
        assert "/help" in message_text
    
    @pytest.mark.asyncio
    async def test_help_command(self, telegram_service, mock_update, mock_context):
        """Test /help command handler."""
        await telegram_service._handle_help(mock_update, mock_context)
        
        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        message_text = call_args[0][0]
        
        assert "Available Commands" in message_text
        assert "/status" in message_text
        assert "/portfolio" in message_text
    
    @pytest.mark.asyncio
    async def test_status_command(self, telegram_service, mock_update, mock_context):
        """Test /status command handler."""
        await telegram_service._handle_status(mock_update, mock_context)
        
        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        message_text = call_args[0][0]
        
        assert "Trading System Status" in message_text
        assert "100000.00" in message_text
        assert "500.00" in message_text
        telegram_service.trading_system.get_status.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_status_command_no_trading_system(self, telegram_service, mock_update, mock_context):
        """Test /status command when trading system is not available."""
        telegram_service.trading_system = None
        
        await telegram_service._handle_status(mock_update, mock_context)
        
        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        message_text = call_args[0][0]
        
        assert "Trading system not available" in message_text
    
    @pytest.mark.asyncio
    async def test_portfolio_command(self, telegram_service, mock_update, mock_context):
        """Test /portfolio command handler."""
        # Mock portfolio data
        positions = [
            Position(
                symbol="AAPL",
                quantity=Decimal("100"),
                market_value=Decimal("15000.00"),
                avg_entry_price=Decimal("150.00"),
                side=PositionSide.LONG,
                unrealized_pnl=Decimal("500.00"),
                unrealized_pnl_percentage=Decimal("0.033")
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
        
        telegram_service.trading_system.get_portfolio.return_value = portfolio
        
        await telegram_service._handle_portfolio(mock_update, mock_context)
        
        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        message_text = call_args[0][0]
        
        assert "Portfolio Summary" in message_text
        assert "25000.00" in message_text
        assert "AAPL" in message_text
        telegram_service.trading_system.get_portfolio.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_send_order_notification(self, telegram_service):
        """Test sending order notification."""
        order = Order(
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("100"),
            id="order_123"
        )
        
        telegram_service.bot = Mock()
        telegram_service.bot.send_message = AsyncMock()
        
        result = await telegram_service.send_order_notification(order, "created")
        
        assert result is True
        telegram_service.bot.send_message.assert_called_once()
        call_args = telegram_service.bot.send_message.call_args
        message_text = call_args[1]['text']
        
        assert "Order Created" in message_text
        assert "AAPL" in message_text
        assert "BUY" in message_text
        assert "100" in message_text
    
    @pytest.mark.asyncio
    async def test_send_portfolio_update(self, telegram_service):
        """Test sending portfolio update."""
        portfolio = Portfolio(
            equity=Decimal("25000.00"),
            cash=Decimal("7500.00"),
            market_value=Decimal("17500.00"),
            day_pnl=Decimal("500.00"),
            total_pnl=Decimal("2500.00"),
            positions=[]
        )
        
        telegram_service.bot = Mock()
        telegram_service.bot.send_message = AsyncMock()
        
        result = await telegram_service.send_portfolio_update(portfolio)
        
        assert result is True
        telegram_service.bot.send_message.assert_called_once()
        call_args = telegram_service.bot.send_message.call_args
        message_text = call_args[1]['text']
        
        assert "Portfolio Update" in message_text
        assert "25000.00" in message_text
    
    @pytest.mark.asyncio
    async def test_send_system_alert(self, telegram_service):
        """Test sending system alert."""
        telegram_service.bot = Mock()
        telegram_service.bot.send_message = AsyncMock()
        
        result = await telegram_service.send_system_alert("Test alert", "warning")
        
        assert result is True
        telegram_service.bot.send_message.assert_called_once()
        call_args = telegram_service.bot.send_message.call_args
        message_text = call_args[1]['text']
        
        assert "WARNING" in message_text
        assert "Test alert" in message_text
    
    @pytest.mark.asyncio
    async def test_unauthorized_access(self, telegram_service, mock_update, mock_context):
        """Test unauthorized access handling."""
        # Change chat ID to unauthorized
        telegram_service.chat_id = "authorized_chat_id"
        mock_update.effective_chat.id = "unauthorized_chat_id"
        
        await telegram_service._handle_start(mock_update, mock_context)
        
        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        message_text = call_args[0][0]
        
        assert "Unauthorized access" in message_text
    
    def test_get_transport_info(self, telegram_service):
        """Test get_transport_info method."""
        info = telegram_service.get_transport_info()
        
        assert info['name'] == "Telegram Service"
        assert info['type'] == "combined_transport_bot"
        assert 'status' in info
        assert 'commands' in info
        assert info['status']['trading_system_connected'] is True


class TestTelegramServiceIntegration:
    """Integration tests for TelegramService."""
    
    @pytest.mark.asyncio
    async def test_command_registration(self):
        """Test that commands are properly registered."""
        with patch('telegram.Bot') as mock_bot:
            with patch('telegram.ext.Application') as mock_app:
                mock_app.builder.return_value.token.return_value.build.return_value = mock_app.return_value
                
                service = TelegramService()
                await service.initialize()
                
                # Check that handlers were registered
                assert service.application is not None
    
    @pytest.mark.asyncio
    async def test_end_to_end_message_flow(self):
        """Test end-to-end message flow."""
        with patch('telegram.Bot') as mock_bot:
            trading_system = Mock()
            trading_system.get_status = AsyncMock(return_value={
                'status': 'running',
                'trading_enabled': True,
                'market_open': True,
                'equity': Decimal('100000.00'),
                'day_pnl': Decimal('500.00'),
                'active_orders': 0,
                'positions': 0,
                'last_update': '2023-01-01 12:00:00'
            })
            
            service = TelegramService(trading_system=trading_system)
            service.bot = Mock()
            service.bot.send_message = AsyncMock()
            
            # Test sending message
            result = await service.send_message("Test notification")
            assert result is True
            
            # Test command handling
            update = Mock()
            update.effective_chat.id = "test_chat_id"
            update.message.reply_text = AsyncMock()
            context = Mock()
            
            await service._handle_status(update, context)
            
            # Verify that status was called and response was sent
            trading_system.get_status.assert_called_once()
            update.message.reply_text.assert_called_once()


@pytest.mark.integration
class TestTelegramServiceRealIntegration:
    """Real integration tests (requires actual Telegram credentials)."""
    
    @pytest.mark.skip(reason="Requires real Telegram credentials")
    @pytest.mark.asyncio
    async def test_real_telegram_connection(self):
        """Test real Telegram connection."""
        # This test requires actual Telegram bot token and chat ID
        # Should be enabled only when testing with real credentials
        pass
    
    @pytest.mark.skip(reason="Requires real Telegram credentials")
    @pytest.mark.asyncio
    async def test_real_message_sending(self):
        """Test real message sending."""
        # This test requires actual Telegram bot token and chat ID
        # Should be enabled only when testing with real credentials
        pass 