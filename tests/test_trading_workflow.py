"""
Unit tests for trading workflow and LLM provider configuration.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from src.agents.trading_workflow import create_llm_client, TradingWorkflow
from src.apis.alpaca_api import AlpacaAPI
from src.apis.tiingo_api import TiingoAPI
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