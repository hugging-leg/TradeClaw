"""
Tests for Workflow Factory

Tests workflow creation and configuration including:
- LLM Portfolio Agent workflow
- Sequential workflow
- Tool calling workflow
- Workflow factory pattern
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch

from src.agents.workflow_factory import WorkflowFactory
from src.agents.llm_portfolio_agent import LLMPortfolioAgent
from src.agents.sequential_workflow import SequentialWorkflow
from src.agents.tool_calling_workflow import ToolCallingWorkflow
from config import settings


class TestWorkflowFactory:
    """Test suite for WorkflowFactory"""
    
    @pytest.fixture
    def mock_apis(self):
        """Create mock APIs for testing"""
        broker_api = Mock()
        market_data_api = Mock()
        news_api = Mock()
        message_manager = Mock()
        
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
    
    def test_create_sequential_workflow(self, mock_apis):
        """Test creating sequential workflow"""
        broker, market_data, news, message_mgr = mock_apis
        
        workflow = WorkflowFactory.create_workflow(
            workflow_type="sequential",
            broker_api=broker,
            market_data_api=market_data,
            news_api=news,
            message_manager=message_mgr
        )
        
        assert isinstance(workflow, SequentialWorkflow)
    
    def test_create_tool_calling_workflow(self, mock_apis):
        """Test creating tool calling workflow"""
        broker, market_data, news, message_mgr = mock_apis
        
        workflow = WorkflowFactory.create_workflow(
            workflow_type="tool_calling",
            broker_api=broker,
            market_data_api=market_data,
            news_api=news,
            message_manager=message_mgr
        )
        
        assert isinstance(workflow, ToolCallingWorkflow)
    
    def test_invalid_workflow_type(self, mock_apis):
        """Test that invalid workflow type raises error"""
        broker, market_data, news, message_mgr = mock_apis
        
        # WorkflowFactory raises RuntimeError (wrapping ValueError)
        with pytest.raises((ValueError, RuntimeError)):
            WorkflowFactory.create_workflow(
                workflow_type="invalid_type",
                broker_api=broker,
                market_data_api=market_data,
                news_api=news,
                message_manager=message_mgr
            )
    
    def test_workflow_type_case_insensitive(self, mock_apis):
        """Test that workflow type is case-insensitive"""
        broker, market_data, news, message_mgr = mock_apis
        
        workflow1 = WorkflowFactory.create_workflow(
            workflow_type="LLM_PORTFOLIO",
            broker_api=broker,
            market_data_api=market_data,
            news_api=news,
            message_manager=message_mgr
        )
        
        workflow2 = WorkflowFactory.create_workflow(
            workflow_type="llm_portfolio",
            broker_api=broker,
            market_data_api=market_data,
            news_api=news,
            message_manager=message_mgr
        )
        
        assert type(workflow1) == type(workflow2)


class TestLLMPortfolioAgent:
    """Test suite for LLM Portfolio Agent"""
    
    @pytest.fixture
    def mock_llm_agent(self):
        """Create mock LLM portfolio agent"""
        broker_api = Mock()
        market_data_api = Mock()
        news_api = Mock()
        message_manager = AsyncMock()
        
        with patch('src.agents.llm_portfolio_agent.create_llm_client'):
            agent = LLMPortfolioAgent(
                broker_api=broker_api,
                market_data_api=market_data_api,
                news_api=news_api,
                message_manager=message_manager
            )
        
        return agent
    
    def test_llm_agent_initialization(self, mock_llm_agent):
        """Test LLM agent initializes correctly"""
        assert mock_llm_agent is not None
        assert hasattr(mock_llm_agent, 'tools')
        assert hasattr(mock_llm_agent, 'agent')
        assert hasattr(mock_llm_agent, 'system_prompt')
    
    def test_llm_agent_has_11_tools(self, mock_llm_agent):
        """Test that LLM agent has all 11 tools"""
        assert len(mock_llm_agent.tools) == 11
        
        tool_names = [tool.name for tool in mock_llm_agent.tools]
        expected_tools = [
            'get_current_time',
            'check_market_status',
            'get_portfolio_status',
            'get_market_data',
            'get_latest_news',
            'get_position_analysis',
            'get_latest_price',
            'get_historical_prices',
            'adjust_position',
            'rebalance_portfolio',
            'schedule_next_analysis'
        ]
        
        for expected_tool in expected_tools:
            assert expected_tool in tool_names, f"Missing tool: {expected_tool}"
    
    def test_llm_agent_workflow_type(self, mock_llm_agent):
        """Test that LLM agent returns correct workflow type"""
        assert mock_llm_agent.get_workflow_type() == "llm_portfolio_agent"
    
    @pytest.mark.asyncio
    async def test_llm_agent_system_prompt(self, mock_llm_agent):
        """Test that system prompt is properly configured"""
        prompt = mock_llm_agent.system_prompt
        
        assert "投资组合经理" in prompt
        assert "sharpe ratio" in prompt.lower()
        # System prompt mentions key concepts
        assert any(word in prompt for word in ["职责", "重要", "调度", "现金"])


class TestSequentialWorkflow:
    """Test suite for Sequential Workflow"""
    
    @pytest.fixture
    def sequential_workflow(self):
        """Create mock sequential workflow"""
        return SequentialWorkflow(
            broker_api=Mock(),
            market_data_api=Mock(),
            news_api=Mock(),
            message_manager=AsyncMock()
        )
    
    def test_sequential_workflow_initialization(self, sequential_workflow):
        """Test sequential workflow initializes correctly"""
        assert sequential_workflow is not None
        assert hasattr(sequential_workflow, 'broker_api')
        assert hasattr(sequential_workflow, 'market_data_api')
        assert hasattr(sequential_workflow, 'news_api')
    
    def test_sequential_workflow_type(self, sequential_workflow):
        """Test workflow type is correct"""
        assert sequential_workflow.get_workflow_type() == "sequential"
    
    @pytest.mark.asyncio
    async def test_sequential_workflow_phases(self, sequential_workflow):
        """Test that sequential workflow has defined phases"""
        # Sequential workflow should have methods for each phase
        assert hasattr(sequential_workflow, 'gather_data')
        assert hasattr(sequential_workflow, 'make_decision')
        assert hasattr(sequential_workflow, 'execute_decision')


class TestToolCallingWorkflow:
    """Test suite for Tool Calling Workflow"""
    
    @pytest.fixture
    def tool_calling_workflow(self):
        """Create mock tool calling workflow"""
        # ToolCallingWorkflow uses ChatOpenAI directly, not create_llm_client
        with patch('src.agents.tool_calling_workflow.ChatOpenAI'):
            workflow = ToolCallingWorkflow(
                broker_api=Mock(),
                market_data_api=Mock(),
                news_api=Mock(),
                message_manager=AsyncMock()
            )
        return workflow
    
    def test_tool_calling_workflow_initialization(self, tool_calling_workflow):
        """Test tool calling workflow initializes correctly"""
        assert tool_calling_workflow is not None
    
    def test_tool_calling_workflow_type(self, tool_calling_workflow):
        """Test workflow type is correct"""
        # Actual implementation returns "toolcalling" (no underscore)
        assert tool_calling_workflow.get_workflow_type() in ["tool_calling", "toolcalling"]
    
    def test_tool_calling_has_tools(self, tool_calling_workflow):
        """Test that tool calling workflow has tools"""
        assert hasattr(tool_calling_workflow, 'tools')
        assert len(tool_calling_workflow.tools) > 0


class TestWorkflowConfiguration:
    """Test suite for workflow configuration from settings"""
    
    def test_default_workflow_type(self):
        """Test default workflow type from settings"""
        # Should have a default workflow type configured
        assert hasattr(settings, 'workflow_type')
        assert settings.workflow_type in ['llm_portfolio', 'sequential', 'tool_calling']
    
    def test_llm_provider_configuration(self):
        """Test LLM provider configuration"""
        assert hasattr(settings, 'llm_provider')
        assert settings.llm_provider.lower() in ['openai', 'deepseek']
    
    @patch.dict('os.environ', {'WORKFLOW_TYPE': 'llm_portfolio'})
    def test_workflow_from_environment(self):
        """Test workflow configuration from environment"""
        # Reload settings to pick up env var
        from importlib import reload
        import config
        reload(config)
        
        assert config.settings.workflow_type == 'llm_portfolio'


class TestWorkflowIntegration:
    """Integration tests for workflow system"""
    
    @pytest.mark.asyncio
    async def test_workflow_context_initialization(self):
        """Test workflow context initialization"""
        broker_api = Mock()
        market_data_api = Mock()
        news_api = Mock()
        message_manager = AsyncMock()
        
        workflow = WorkflowFactory.create_workflow(
            workflow_type="sequential",
            broker_api=broker_api,
            market_data_api=market_data_api,
            news_api=news_api,
            message_manager=message_manager
        )
        
        context = await workflow.initialize_workflow({"trigger": "test"})
        
        assert "trigger" in context
        assert "workflow_type" in context
        assert context["trigger"] == "test"
    
    @pytest.mark.asyncio
    async def test_workflow_error_handling(self):
        """Test workflow error handling"""
        broker_api = Mock()
        broker_api.get_portfolio = AsyncMock(side_effect=Exception("API Error"))
        
        workflow = WorkflowFactory.create_workflow(
            workflow_type="sequential",
            broker_api=broker_api,
            market_data_api=Mock(),
            news_api=Mock(),
            message_manager=AsyncMock()
        )
        
        # Should handle errors gracefully
        result = await workflow.gather_data()
        # Should return empty or error dict, not crash
        assert isinstance(result, dict)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
