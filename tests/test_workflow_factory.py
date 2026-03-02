"""
Tests for Workflow Factory

Tests workflow creation and configuration including:
- LLM Portfolio Agent workflow
- Workflow factory pattern
- Workflow registration and discovery
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch

from agent_trader.agents.workflow_factory import (
    WorkflowFactory,
    get_registered_workflows,
    get_workflow_choices,
)
from agent_trader.agents.llm_portfolio_agent import LLMPortfolioAgent
from config import settings


class TestWorkflowFactory:
    """Test suite for WorkflowFactory"""
    
    @pytest.fixture
    def mock_apis(self):
        """Create mock APIs for testing"""
        broker_api = Mock()
        market_data_api = Mock()
        news_api = Mock()
        message_manager = AsyncMock()
        
        return broker_api, market_data_api, news_api, message_manager
    
    def test_create_llm_portfolio_workflow(self, mock_apis):
        """Test creating LLM portfolio agent workflow"""
        broker, market_data, news, message_mgr = mock_apis
        
        workflow = WorkflowFactory.create_workflow(
            workflow_type="llm_portfolio",
            broker_api=broker,
            market_data_api=market_data,
            news_api=news,
            message_manager=message_mgr
        )
        
        assert isinstance(workflow, LLMPortfolioAgent)
        assert workflow.broker_api == broker
        assert workflow.market_data_api == market_data
        assert workflow.news_api == news
        assert workflow.message_manager == message_mgr
    
    def test_invalid_workflow_type(self, mock_apis):
        """Test that invalid workflow type raises error"""
        broker, market_data, news, message_mgr = mock_apis
        
        with pytest.raises((ValueError, RuntimeError)):
            WorkflowFactory.create_workflow(
                workflow_type="invalid_type",
                broker_api=broker,
                market_data_api=market_data,
                news_api=news,
                message_manager=message_mgr
            )
    
    def test_available_workflows(self):
        """Test getting available workflows"""
        available = WorkflowFactory.get_available_workflows()
        
        assert isinstance(available, dict)
        assert "llm_portfolio" in available
        
        # Each entry should have expected metadata
        for name, info in available.items():
            assert "name" in info
            assert "class" in info
            assert "description" in info
    
    def test_is_supported(self):
        """Test is_supported check"""
        assert WorkflowFactory.is_supported("llm_portfolio") is True
        assert WorkflowFactory.is_supported("nonexistent_workflow") is False
    
    def test_get_workflow_choices(self):
        """Test getting workflow choices list"""
        choices = get_workflow_choices()
        
        assert isinstance(choices, list)
        assert "llm_portfolio" in choices
    
    def test_get_registered_workflows(self):
        """Test getting registered workflows dict"""
        workflows = get_registered_workflows()
        
        assert isinstance(workflows, dict)
        assert "llm_portfolio" in workflows
        assert workflows["llm_portfolio"] == LLMPortfolioAgent


class TestLLMPortfolioAgent:
    """Test suite for LLM Portfolio Agent"""
    
    @pytest.fixture
    def llm_agent(self):
        """Create LLM portfolio agent with mock dependencies"""
        broker_api = Mock()
        market_data_api = Mock()
        news_api = Mock()
        message_manager = AsyncMock()
        
        agent = LLMPortfolioAgent(
            broker_api=broker_api,
            market_data_api=market_data_api,
            news_api=news_api,
            message_manager=message_manager,
        )
        
        return agent
    
    def test_llm_agent_initialization(self, llm_agent):
        """Test LLM agent initializes correctly"""
        assert llm_agent is not None
        assert hasattr(llm_agent, 'broker_api')
        assert hasattr(llm_agent, 'market_data_api')
        assert hasattr(llm_agent, 'news_api')
        assert hasattr(llm_agent, 'message_manager')
    
    def test_llm_agent_workflow_type(self, llm_agent):
        """Test that LLM agent returns correct workflow type"""
        assert llm_agent.get_workflow_type() == "llm_portfolio"
    
    def test_llm_agent_has_config(self, llm_agent):
        """Test that LLM agent has default config"""
        config = llm_agent.get_config()
        
        assert isinstance(config, dict)
        assert "system_prompt" in config
    
    def test_llm_agent_system_prompt(self, llm_agent):
        """Test that system prompt is properly configured"""
        config = llm_agent.get_config()
        prompt = config["system_prompt"]
        
        assert "投资组合经理" in prompt
        assert "sharpe ratio" in prompt.lower()
    
    def test_llm_agent_update_config(self, llm_agent):
        """Test that config can be updated"""
        original_config = llm_agent.get_config()
        
        llm_agent.update_config({"llm_recursion_limit": 50})
        
        updated_config = llm_agent.get_config()
        assert updated_config.get("llm_recursion_limit") == 50


class TestWorkflowConfiguration:
    """Test suite for workflow configuration from settings"""
    
    def test_default_workflow_type(self):
        """Test default workflow type from settings"""
        assert hasattr(settings, 'workflow_type')
        assert settings.workflow_type is not None
    
    def test_workflow_type_is_registered(self):
        """Test that the configured workflow type is actually registered"""
        choices = get_workflow_choices()
        assert settings.workflow_type in choices


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
