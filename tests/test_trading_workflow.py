"""
Unit tests for trading workflow and LLM provider configuration.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from decimal import Decimal
from src.agents.trading_workflow import create_llm_client, TradingWorkflow
from src.apis.telegram_message_queue import TelegramMessageQueue
from src.apis.alpaca_api import AlpacaAPI
from src.apis.tiingo_api import TiingoAPI
from src.models.trading_models import TradingDecision, TradingAction
from config import settings


class TestLLMProviderConfiguration:
    """Test LLM provider configuration and factory function"""
    
    def test_create_llm_client_openai(self):
        """Test creating OpenAI LLM client"""
        with patch('config.settings') as mock_settings:
            mock_settings.llm_provider = "openai"
            mock_settings.openai_model = "gpt-4"
            mock_settings.openai_api_key = "test_key"
            
            with patch('src.agents.trading_workflow.ChatOpenAI') as mock_chat_openai:
                mock_instance = Mock()
                mock_chat_openai.return_value = mock_instance
                
                client = create_llm_client()
                
                mock_chat_openai.assert_called_once_with(
                    model="gpt-4",
                    api_key="test_key",
                    temperature=0.1
                )
                assert client == mock_instance
    
    def test_create_llm_client_deepseek(self):
        """Test creating DeepSeek LLM client"""
        with patch('config.settings') as mock_settings:
            mock_settings.llm_provider = "deepseek"
            mock_settings.deepseek_model = "deepseek-chat"
            mock_settings.deepseek_api_key = "test_deepseek_key"
            
            with patch('src.agents.trading_workflow.ChatDeepSeek') as mock_chat_deepseek:
                mock_instance = Mock()
                mock_chat_deepseek.return_value = mock_instance
                
                client = create_llm_client()
                
                mock_chat_deepseek.assert_called_once_with(
                    model="deepseek-chat",
                    api_key="test_deepseek_key",
                    temperature=0.1
                )
                assert client == mock_instance
    
    def test_create_llm_client_unknown_provider(self):
        """Test creating LLM client with unknown provider defaults to OpenAI"""
        with patch('config.settings') as mock_settings:
            mock_settings.llm_provider = "unknown_provider"
            mock_settings.openai_model = "gpt-4"
            mock_settings.openai_api_key = "test_key"
            
            with patch('src.agents.trading_workflow.ChatOpenAI') as mock_chat_openai:
                mock_instance = Mock()
                mock_chat_openai.return_value = mock_instance
                
                with patch('src.agents.trading_workflow.logger') as mock_logger:
                    client = create_llm_client()
                    
                    mock_logger.warning.assert_called_once_with(
                        "Unknown LLM provider: unknown_provider. Defaulting to OpenAI."
                    )
                    mock_chat_openai.assert_called_once_with(
                        model="gpt-4",
                        api_key="test_key",
                        temperature=0.1
                    )
                    assert client == mock_instance
    
    def test_trading_workflow_initialization_with_deepseek(self):
        """Test TradingWorkflow initialization with DeepSeek provider"""
        with patch('config.settings') as mock_settings:
            mock_settings.llm_provider = "deepseek"
            mock_settings.deepseek_model = "deepseek-chat"
            mock_settings.deepseek_api_key = "test_deepseek_key"
            
            with patch('src.agents.trading_workflow.ChatDeepSeek') as mock_chat_deepseek:
                mock_llm_instance = Mock()
                mock_chat_deepseek.return_value = mock_llm_instance
                
                mock_alpaca_api = Mock(spec=AlpacaAPI)
                mock_tiingo_api = Mock(spec=TiingoAPI)
                
                workflow = TradingWorkflow(mock_alpaca_api, mock_tiingo_api)
                
                assert workflow.llm == mock_llm_instance
                assert workflow.alpaca_api == mock_alpaca_api
                assert workflow.tiingo_api == mock_tiingo_api
                assert workflow.workflow is not None
    
    def test_trading_workflow_initialization_with_openai(self):
        """Test TradingWorkflow initialization with OpenAI provider"""
        with patch('config.settings') as mock_settings:
            mock_settings.llm_provider = "openai"
            mock_settings.openai_model = "gpt-4"
            mock_settings.openai_api_key = "test_key"
            
            with patch('src.agents.trading_workflow.ChatOpenAI') as mock_chat_openai:
                mock_llm_instance = Mock()
                mock_chat_openai.return_value = mock_llm_instance
                
                mock_alpaca_api = Mock(spec=AlpacaAPI)
                mock_tiingo_api = Mock(spec=TiingoAPI)
                
                workflow = TradingWorkflow(mock_alpaca_api, mock_tiingo_api)
                
                assert workflow.llm == mock_llm_instance
                assert workflow.alpaca_api == mock_alpaca_api
                assert workflow.tiingo_api == mock_tiingo_api
                assert workflow.workflow is not None


class TestTradingDecisionParsing:
    """Test decision parsing logic"""
    
    @pytest.fixture
    def workflow(self):
        """Create a TradingWorkflow instance for testing"""
        mock_alpaca_api = Mock(spec=AlpacaAPI)
        mock_tiingo_api = Mock(spec=TiingoAPI)
        
        with patch('src.agents.trading_workflow.create_llm_client') as mock_create_llm:
            mock_llm = Mock()
            mock_create_llm.return_value = mock_llm
            return TradingWorkflow(mock_alpaca_api, mock_tiingo_api)
    
    def test_parse_decision_hold(self, workflow):
        """Test parsing HOLD decision"""
        decision_text = """
DECISION: HOLD
SYMBOL: N/A
QUANTITY: N/A
REASONING: Market conditions are uncertain and current portfolio allocation is balanced
CONFIDENCE: 0.75
"""
        
        decision = workflow._parse_decision(decision_text)
        
        assert decision.action == TradingAction.HOLD
        assert decision.symbol == ""  # Should be empty string for HOLD decisions
        assert decision.quantity is None
        assert "Market conditions are uncertain" in decision.reasoning
        assert decision.confidence == Decimal('0.75')
    
    def test_parse_decision_buy(self, workflow):
        """Test parsing BUY decision"""
        decision_text = """
DECISION: BUY
SYMBOL: AAPL
QUANTITY: 50
REASONING: Strong earnings and positive technical indicators
CONFIDENCE: 0.85
"""
        
        decision = workflow._parse_decision(decision_text)
        
        assert decision.action == TradingAction.BUY
        assert decision.symbol == "AAPL"
        assert decision.quantity == Decimal("50")
        assert "Strong earnings" in decision.reasoning
        assert decision.confidence == Decimal('0.85')
    
    def test_parse_decision_sell(self, workflow):
        """Test parsing SELL decision"""
        decision_text = """
DECISION: SELL
SYMBOL: TSLA
QUANTITY: 25
REASONING: Overvalued position reaching take-profit target
CONFIDENCE: 0.90
"""
        
        decision = workflow._parse_decision(decision_text)
        
        assert decision.action == "sell"
        assert decision.symbol == "TSLA"
        assert decision.quantity == Decimal("25")
        assert "Overvalued position" in decision.reasoning
        assert decision.confidence == 0.90
    
    def test_parse_decision_hold_with_various_na_formats(self, workflow):
        """Test parsing HOLD decision with different N/A formats"""
        test_cases = [
            "N/A", "NA", "NONE", "NULL", "n/a", "none", "null"
        ]
        
        for na_format in test_cases:
            decision_text = f"""
DECISION: HOLD
SYMBOL: {na_format}
QUANTITY: {na_format}
REASONING: No action recommended
CONFIDENCE: 0.50
"""
            
            decision = workflow._parse_decision(decision_text)
            
            assert decision.action == "hold"
            assert decision.symbol is None
            assert decision.quantity is None
    
    def test_parse_decision_confidence_bounds(self, workflow):
        """Test confidence value bounds checking"""
        # Test confidence > 1.0
        decision_text = """
DECISION: HOLD
SYMBOL: N/A
QUANTITY: N/A
REASONING: Test reasoning
CONFIDENCE: 1.5
"""
        
        decision = workflow._parse_decision(decision_text)
        assert decision.confidence == 1.0  # Should be capped at 1.0
        
        # Test confidence < 0.0
        decision_text = """
DECISION: HOLD
SYMBOL: N/A
QUANTITY: N/A
REASONING: Test reasoning
CONFIDENCE: -0.5
"""
        
        decision = workflow._parse_decision(decision_text)
        assert decision.confidence == 0.0  # Should be floored at 0.0
    
    def test_parse_decision_invalid_confidence(self, workflow):
        """Test handling of invalid confidence values"""
        decision_text = """
DECISION: HOLD
SYMBOL: N/A
QUANTITY: N/A
REASONING: Test reasoning
CONFIDENCE: invalid
"""
        
        decision = workflow._parse_decision(decision_text)
        assert decision.confidence == 0.5  # Should default to 0.5
    
    def test_parse_decision_invalid_quantity(self, workflow):
        """Test handling of invalid quantity values"""
        decision_text = """
DECISION: BUY
SYMBOL: AAPL
QUANTITY: invalid_number
REASONING: Test reasoning
CONFIDENCE: 0.8
"""
        
        decision = workflow._parse_decision(decision_text)
        assert decision.quantity is None  # Should be None for invalid quantity
    
    def test_parse_decision_missing_fields(self, workflow):
        """Test parsing with missing fields"""
        decision_text = """
DECISION: HOLD
REASONING: Minimal decision format
"""
        
        decision = workflow._parse_decision(decision_text)
        
        assert decision.action == "hold"
        assert decision.symbol is None
        assert decision.quantity is None
        assert decision.reasoning == "Minimal decision format"
        assert decision.confidence == 0.5  # Default confidence
    
    def test_parse_decision_error_handling(self, workflow):
        """Test error handling for malformed decision text"""
        decision_text = "This is not a valid decision format"
        
        with patch('src.agents.trading_workflow.logger') as mock_logger:
            decision = workflow._parse_decision(decision_text)
            
            # Should return default HOLD decision
            assert decision.action == "hold"
            assert decision.symbol is None
            assert decision.reasoning == "Error parsing decision from LLM response"
            assert decision.confidence == 0.0
            
            # Should log the error
            mock_logger.error.assert_called()


class TestTelegramMessageQueue:
    """Test Telegram message queue functionality"""
    
    @pytest.fixture
    def mock_telegram_bot(self):
        """Mock Telegram bot"""
        mock_bot = Mock()
        mock_bot.send_message = Mock()
        return mock_bot
    
    def test_message_queue_initialization(self):
        """Test message queue initialization"""
        queue = TelegramMessageQueue()
        assert queue.telegram_bot is None
        assert not queue.is_processing
    
    def test_message_queue_with_bot(self, mock_telegram_bot):
        """Test message queue with Telegram bot"""
        queue = TelegramMessageQueue(mock_telegram_bot)
        assert queue.telegram_bot == mock_telegram_bot
    
    @pytest.mark.asyncio
    async def test_send_decision_summary_hold(self, mock_telegram_bot):
        """Test sending HOLD decision summary"""
        queue = TelegramMessageQueue(mock_telegram_bot)
        
        decision = TradingDecision(
            action="hold",
            symbol=None,
            quantity=None,
            reasoning="Market uncertainty suggests waiting for better opportunities",
            confidence=0.75
        )
        
        await queue.send_decision_summary(decision)
        
        # Should have called send_message
        queue.message_queue.qsize() > 0
    
    @pytest.mark.asyncio
    async def test_send_decision_summary_buy(self, mock_telegram_bot):
        """Test sending BUY decision summary"""
        queue = TelegramMessageQueue(mock_telegram_bot)
        
        decision = TradingDecision(
            action="buy",
            symbol="AAPL",
            quantity=Decimal("50"),
            reasoning="Strong fundamentals and positive technical indicators suggest upward momentum",
            confidence=0.85
        )
        
        await queue.send_decision_summary(decision)
        
        # Should have queued a message
        assert queue.message_queue.qsize() > 0
    
    @pytest.mark.asyncio
    async def test_send_decision_summary_no_decision(self, mock_telegram_bot):
        """Test sending summary with None decision"""
        queue = TelegramMessageQueue(mock_telegram_bot)
        
        await queue.send_decision_summary(None)
        
        # Should have queued a default HOLD message
        assert queue.message_queue.qsize() > 0


class TestTradingWorkflowIntegration:
    """Integration tests for trading workflow"""
    
    @pytest.fixture
    def mock_alpaca_api(self):
        """Mock AlpacaAPI"""
        return Mock(spec=AlpacaAPI)
    
    @pytest.fixture
    def mock_tiingo_api(self):
        """Mock TiingoAPI"""
        return Mock(spec=TiingoAPI)
    
    def test_workflow_graph_construction(self, mock_alpaca_api, mock_tiingo_api):
        """Test that workflow graph is constructed correctly"""
        with patch('src.agents.trading_workflow.create_llm_client') as mock_create_llm:
            mock_llm = Mock()
            mock_create_llm.return_value = mock_llm
            
            workflow = TradingWorkflow(mock_alpaca_api, mock_tiingo_api)
            
            # Verify workflow is built
            assert workflow.workflow is not None
            assert workflow.llm == mock_llm
            
            # Verify tools are initialized
            assert workflow.tools is not None
            assert workflow.tools.alpaca_api == mock_alpaca_api
            assert workflow.tools.tiingo_api == mock_tiingo_api
            
            # Verify message queue is initialized
            assert workflow.message_queue is not None
    
    def test_workflow_with_telegram_bot(self, mock_alpaca_api, mock_tiingo_api):
        """Test workflow initialization with Telegram bot"""
        mock_telegram_bot = Mock()
        
        with patch('src.agents.trading_workflow.create_llm_client') as mock_create_llm:
            mock_llm = Mock()
            mock_create_llm.return_value = mock_llm
            
            workflow = TradingWorkflow(mock_alpaca_api, mock_tiingo_api, mock_telegram_bot)
            
            # Verify telegram bot is passed to message queue
            assert workflow.telegram_bot == mock_telegram_bot
            assert workflow.message_queue.telegram_bot == mock_telegram_bot 