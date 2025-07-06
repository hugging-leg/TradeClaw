"""
Unit tests for workflow factory and related components.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any

from src.agents.workflow_factory import WorkflowFactory, WorkflowType, get_workflow_choices, validate_workflow_config
from src.agents.workflow_base import WorkflowBase
from src.agents.sequential_workflow import SequentialWorkflow
from src.agents.tool_calling_workflow import ToolCallingWorkflow
from src.adapters.brokers.alpaca_adapter import AlpacaBrokerAdapter
from src.adapters.market_data.tiingo_market_data_adapter import TiingoMarketDataAdapter
from src.adapters.news.tiingo_news_adapter import TiingoNewsAdapter
from config import settings


class TestWorkflowFactory:
    """Test WorkflowFactory functionality"""
    
    def test_workflow_type_enum(self):
        """Test WorkflowType enum values"""
        assert WorkflowType.SEQUENTIAL.value == "sequential"
        assert WorkflowType.TOOL_CALLING.value == "tool_calling"
        
        # Test all enum values are strings
        for workflow_type in WorkflowType:
            assert isinstance(workflow_type.value, str)
    
    def test_validate_workflow_type_valid(self):
        """Test validation with valid workflow types"""
        # Test valid types
        assert WorkflowFactory._validate_workflow_type("sequential") == WorkflowType.SEQUENTIAL
        assert WorkflowFactory._validate_workflow_type("tool_calling") == WorkflowType.TOOL_CALLING
        
        # Test case insensitivity
        assert WorkflowFactory._validate_workflow_type("SEQUENTIAL") == WorkflowType.SEQUENTIAL
        assert WorkflowFactory._validate_workflow_type("Tool_Calling") == WorkflowType.TOOL_CALLING
    
    def test_validate_workflow_type_invalid(self):
        """Test validation with invalid workflow types"""
        with pytest.raises(ValueError, match="Unsupported workflow type"):
            WorkflowFactory._validate_workflow_type("invalid_type")
        
        with pytest.raises(ValueError, match="Unsupported workflow type"):
            WorkflowFactory._validate_workflow_type("random")
    
    def test_create_sequential_workflow(self):
        """Test creating sequential workflow"""
        mock_alpaca = Mock(spec=AlpacaBrokerAdapter)
        mock_tiingo = Mock(spec=TiingoMarketDataAdapter)
        mock_telegram = Mock()
        mock_message_manager = Mock()
        
        with patch.object(settings, 'workflow_type', 'sequential'):
            workflow = WorkflowFactory.create_workflow(
                broker_api=mock_alpaca, 
                market_data_api=mock_tiingo, 
                news_api=mock_telegram,
                message_manager=mock_message_manager
            )
        
        assert isinstance(workflow, SequentialWorkflow)
        assert isinstance(workflow, WorkflowBase)
        assert workflow.broker_api == mock_alpaca
        assert workflow.market_data_api == mock_tiingo
        assert workflow.news_api == mock_telegram
        assert workflow.message_manager == mock_message_manager
    
    def test_create_tool_calling_workflow(self):
        """Test creating tool calling workflow"""
        mock_alpaca = Mock(spec=AlpacaBrokerAdapter)
        mock_tiingo = Mock(spec=TiingoMarketDataAdapter)
        mock_telegram = Mock()
        mock_message_manager = Mock()
        
        with patch.object(settings, 'workflow_type', 'tool_calling'):
            workflow = WorkflowFactory.create_workflow(
                broker_api=mock_alpaca, 
                market_data_api=mock_tiingo, 
                news_api=mock_telegram,
                message_manager=mock_message_manager
            )
        
        assert isinstance(workflow, ToolCallingWorkflow)
        assert isinstance(workflow, WorkflowBase)
        assert workflow.broker_api == mock_alpaca
        assert workflow.market_data_api == mock_tiingo
        assert workflow.news_api == mock_telegram
        assert workflow.message_manager == mock_message_manager
    
    def test_create_workflow_with_override(self):
        """Test creating workflow with type override"""
        mock_alpaca = Mock(spec=AlpacaBrokerAdapter)
        mock_tiingo = Mock(spec=TiingoMarketDataAdapter)
        mock_message_manager = Mock()
        
        # Override with specific type regardless of settings
        workflow = WorkflowFactory.create_workflow(
            broker_api=mock_alpaca, 
            market_data_api=mock_tiingo, 
            message_manager=mock_message_manager,
            workflow_type="tool_calling"
        )
        
        assert isinstance(workflow, ToolCallingWorkflow)
    
    def test_create_workflow_invalid_type(self):
        """Test creating workflow with invalid type"""
        mock_alpaca = Mock(spec=AlpacaBrokerAdapter)
        mock_tiingo = Mock(spec=TiingoMarketDataAdapter)
        mock_message_manager = Mock()
        
        with pytest.raises(RuntimeError, match="Workflow creation failed"):
            WorkflowFactory.create_workflow(
                broker_api=mock_alpaca, 
                market_data_api=mock_tiingo, 
                message_manager=mock_message_manager,
                workflow_type="invalid_type"
            )
    
    def test_create_workflow_default_fallback(self):
        """Test creating workflow with default fallback"""
        mock_alpaca = Mock(spec=AlpacaBrokerAdapter)
        mock_tiingo = Mock(spec=TiingoMarketDataAdapter)
        mock_message_manager = Mock()
        
        # Mock settings without workflow_type
        with patch.object(settings, 'workflow_type', None, create=True):
            workflow = WorkflowFactory.create_workflow(
                broker_api=mock_alpaca, 
                market_data_api=mock_tiingo,
                message_manager=mock_message_manager
            )
        
        # Should default to sequential
        assert isinstance(workflow, SequentialWorkflow)
    
    def test_create_workflow_missing_message_manager(self):
        """Test creating workflow without message_manager raises error"""
        mock_alpaca = Mock(spec=AlpacaBrokerAdapter)
        mock_tiingo = Mock(spec=TiingoMarketDataAdapter)
        mock_telegram = Mock()
        
        with pytest.raises(RuntimeError, match="Workflow creation failed"):
            WorkflowFactory.create_workflow(
                broker_api=mock_alpaca, 
                market_data_api=mock_tiingo, 
                news_api=mock_telegram
                # message_manager intentionally omitted
            )
    
    def test_get_available_workflows(self):
        """Test getting available workflows"""
        workflows = WorkflowFactory.get_available_workflows()
        
        assert isinstance(workflows, dict)
        assert "sequential" in workflows
        assert "tool_calling" in workflows
        
        # Check workflow info structure
        seq_info = workflows["sequential"]
        assert "name" in seq_info
        assert "class" in seq_info
        assert "description" in seq_info
        assert "module" in seq_info
        
        assert seq_info["class"] == "SequentialWorkflow"
        assert seq_info["name"] == "Sequential"
    
    def test_is_workflow_supported(self):
        """Test workflow support checking"""
        assert WorkflowFactory.is_workflow_supported("sequential")
        assert WorkflowFactory.is_workflow_supported("tool_calling")
        assert not WorkflowFactory.is_workflow_supported("invalid_type")
        assert not WorkflowFactory.is_workflow_supported("random")
    
    def test_get_default_workflow_type(self):
        """Test getting default workflow type"""
        with patch.object(settings, 'workflow_type', 'tool_calling'):
            assert WorkflowFactory.get_default_workflow_type() == 'tool_calling'
        
        with patch.object(settings, 'workflow_type', None, create=True):
            assert WorkflowFactory.get_default_workflow_type() == 'sequential'
    
    def test_validate_configuration_valid(self):
        """Test configuration validation with valid settings"""
        with patch.object(settings, 'workflow_type', 'sequential'), \
             patch.object(settings, 'llm_provider', 'openai'), \
             patch.object(settings, 'openai_api_key', 'test_key'):
            
            result = WorkflowFactory.validate_configuration()
            
            assert result["valid"] is True
            assert len(result["errors"]) == 0
            assert result["config"]["workflow_type"] == "sequential"
            assert result["config"]["llm_provider"] == "openai"
    
    def test_validate_configuration_invalid_workflow(self):
        """Test configuration validation with invalid workflow type"""
        with patch.object(settings, 'workflow_type', 'invalid_type'):
            result = WorkflowFactory.validate_configuration()
            
            assert result["valid"] is False
            assert len(result["errors"]) > 0
            assert any("Unsupported workflow type" in error for error in result["errors"])
    
    def test_validate_configuration_missing_api_key(self):
        """Test configuration validation with missing API key"""
        with patch.object(settings, 'workflow_type', 'sequential'), \
             patch.object(settings, 'llm_provider', 'openai'), \
             patch.object(settings, 'openai_api_key', None):
            
            result = WorkflowFactory.validate_configuration()
            
            assert result["valid"] is False
            assert any("Missing required configuration: openai_api_key" in error for error in result["errors"])
    
    def test_validate_configuration_warnings(self):
        """Test configuration validation warnings"""
        with patch.object(settings, 'workflow_type', 'tool_calling'), \
             patch.object(settings, 'llm_provider', 'unsupported_provider'), \
             patch.object(settings, 'openai_api_key', 'test_key'):
            
            result = WorkflowFactory.validate_configuration()
            
            assert len(result["warnings"]) > 0
            assert any("Tool calling workflow works best" in warning for warning in result["warnings"])
    
    def test_create_workflow_info_sequential(self):
        """Test creating workflow info for sequential type"""
        info = WorkflowFactory.create_workflow_info("sequential")
        
        assert info["type"] == "sequential"
        assert info["name"] == "Sequential"
        assert info["class_name"] == "SequentialWorkflow"
        assert info["supported"] is True
        assert "features" in info
        assert "best_for" in info
        
        # Check specific features
        assert "Fixed execution sequence" in info["features"]
        assert "Predictable workflow steps" in info["features"]
    
    def test_create_workflow_info_tool_calling(self):
        """Test creating workflow info for tool calling type"""
        info = WorkflowFactory.create_workflow_info("tool_calling")
        
        assert info["type"] == "tool_calling"
        assert info["name"] == "Tool Calling"
        assert info["class_name"] == "ToolCallingWorkflow"
        assert info["supported"] is True
        assert "features" in info
        assert "best_for" in info
        
        # Check specific features
        assert "Dynamic tool selection" in info["features"]
        assert "LLM-driven decision making" in info["features"]
    
    def test_create_workflow_info_invalid(self):
        """Test creating workflow info for invalid type"""
        info = WorkflowFactory.create_workflow_info("invalid_type")
        
        assert info["type"] == "invalid_type"
        assert info["supported"] is False
        assert "error" in info
    
    def test_register_workflow(self):
        """Test registering new workflow type"""
        # Create a mock workflow class
        class TestWorkflow(WorkflowBase):
            async def run_workflow(self, initial_context=None):
                return {}
            
            async def initialize_workflow(self, context):
                return context
            
            async def gather_data(self):
                return {}
            
            async def make_decision(self, data):
                return None
            
            async def execute_decision(self, decision):
                return {}
        
        # Test successful registration
        test_type = WorkflowType.SEQUENTIAL  # Use existing enum for test
        original_class = WorkflowFactory._workflow_registry[test_type]
        
        try:
            WorkflowFactory.register_workflow(test_type, TestWorkflow)
            assert WorkflowFactory._workflow_registry[test_type] == TestWorkflow
        finally:
            # Restore original
            WorkflowFactory._workflow_registry[test_type] = original_class
    
    def test_register_workflow_invalid_class(self):
        """Test registering invalid workflow class"""
        class InvalidWorkflow:
            pass
        
        with pytest.raises(TypeError, match="must inherit from WorkflowBase"):
            WorkflowFactory.register_workflow(WorkflowType.SEQUENTIAL, InvalidWorkflow)  # type: ignore


class TestConvenienceFunctions:
    """Test convenience functions"""
    
    def test_create_workflow_convenience(self):
        """Test WorkflowFactory.create_workflow convenience method"""
        mock_alpaca = Mock(spec=AlpacaBrokerAdapter)
        mock_tiingo = Mock(spec=TiingoMarketDataAdapter)
        mock_telegram = Mock()
        mock_message_manager = Mock()
        
        with patch.object(settings, 'workflow_type', 'sequential'):
            workflow = WorkflowFactory.create_workflow(
                broker_api=mock_alpaca, 
                market_data_api=mock_tiingo, 
                news_api=mock_telegram,
                message_manager=mock_message_manager
            )
        
        assert isinstance(workflow, SequentialWorkflow)
    
    def test_get_workflow_choices(self):
        """Test get_workflow_choices function"""
        choices = get_workflow_choices()
        
        assert isinstance(choices, list)
        assert "sequential" in choices
        assert "tool_calling" in choices
        assert len(choices) == len(WorkflowType)
    
    def test_validate_workflow_config(self):
        """Test validate_workflow_config function"""
        with patch.object(settings, 'workflow_type', 'sequential'), \
             patch.object(settings, 'llm_provider', 'openai'), \
             patch.object(settings, 'openai_api_key', 'test_key'):
            
            assert validate_workflow_config() is True
        
        with patch.object(settings, 'workflow_type', 'invalid_type'):
            assert validate_workflow_config() is False


class TestWorkflowIntegration:
    """Integration tests for workflow factory and workflows"""
    
    def test_workflow_interface_compatibility(self):
        """Test that all workflows implement the required interface"""
        mock_alpaca = Mock(spec=AlpacaBrokerAdapter)
        mock_tiingo = Mock(spec=TiingoMarketDataAdapter)
        mock_message_manager = Mock()
        
        for workflow_type in WorkflowType:
            workflow = WorkflowFactory.create_workflow(
                broker_api=mock_alpaca, 
                market_data_api=mock_tiingo, 
                message_manager=mock_message_manager,
                workflow_type=workflow_type.value
            )
            
            # Test required interface methods exist
            assert hasattr(workflow, 'run_workflow')
            assert hasattr(workflow, 'initialize_workflow')
            assert hasattr(workflow, 'gather_data')
            assert hasattr(workflow, 'make_decision')
            assert hasattr(workflow, 'execute_decision')
            assert hasattr(workflow, 'get_workflow_type')
            
            # Test workflow type method
            assert isinstance(workflow.get_workflow_type(), str)
    
    @pytest.mark.asyncio
    async def test_workflow_base_methods(self):
        """Test WorkflowBase common methods"""
        mock_alpaca = Mock(spec=AlpacaBrokerAdapter)
        mock_tiingo = Mock(spec=TiingoMarketDataAdapter)
        mock_message_manager = Mock()
        
        workflow = WorkflowFactory.create_workflow(
            broker_api=mock_alpaca, 
            market_data_api=mock_tiingo, 
            message_manager=mock_message_manager,
            workflow_type="sequential"
        )
        
        # Test utility methods exist and can be called
        assert hasattr(workflow, 'send_workflow_start_notification')
        assert hasattr(workflow, 'send_workflow_complete_notification')
        assert hasattr(workflow, '_generate_workflow_id')
        assert hasattr(workflow, '_update_context')
        
        # Test workflow ID generation
        workflow_id = workflow._generate_workflow_id()
        assert isinstance(workflow_id, str)
        assert "sequential" in workflow_id
        
        # Test context update
        test_context = {"test": "value"}
        updated_context = workflow._update_context(test_context)
        assert updated_context["test"] == "value"
        assert workflow.current_context["test"] == "value" 