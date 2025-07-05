"""
Workflow factory for creating different types of trading workflows.

This module implements the Factory pattern to create and manage different
workflow implementations. It provides a centralized way to instantiate
workflows based on configuration settings.

Supported workflow types:
- sequential: Fixed-step workflow (original logic)
- tool_calling: Dynamic workflow using LLM tool calling
- (future) multi_agent: Multi-agent collaborative workflow
"""

import logging
from typing import Dict, Any, Type, Optional
from enum import Enum

from config import settings
from src.apis.alpaca_api import AlpacaAPI
from src.apis.tiingo_api import TiingoAPI
from src.agents.workflow_base import WorkflowBase
from src.agents.sequential_workflow import SequentialWorkflow
from src.agents.tool_calling_workflow import ToolCallingWorkflow


logger = logging.getLogger(__name__)


class WorkflowType(Enum):
    """Enumeration of available workflow types."""
    SEQUENTIAL = "sequential"
    TOOL_CALLING = "tool_calling"
    # Future workflow types
    # MULTI_AGENT = "multi_agent"
    # REINFORCEMENT_LEARNING = "rl"


class WorkflowFactory:
    """
    Factory class for creating trading workflows.
    
    This factory creates different types of workflows based on configuration
    settings and provides a unified interface for workflow instantiation.
    
    Features:
    - Type-safe workflow creation
    - Configuration validation
    - Dependency injection
    - Support for future workflow types
    - Centralized workflow management
    """
    
    # Registry of available workflow implementations
    _workflow_registry: Dict[WorkflowType, Type[WorkflowBase]] = {
        WorkflowType.SEQUENTIAL: SequentialWorkflow,
        WorkflowType.TOOL_CALLING: ToolCallingWorkflow,
    }
    
    @classmethod
    def create_workflow(
        cls,
        alpaca_api: AlpacaAPI,
        tiingo_api: TiingoAPI,
        telegram_bot=None,
        workflow_type: Optional[str] = None
    ) -> WorkflowBase:
        """
        Create a workflow instance based on configuration or specified type.
        
        Args:
            alpaca_api: Alpaca API client
            tiingo_api: Tiingo API client  
            telegram_bot: Optional Telegram bot instance
            workflow_type: Optional workflow type override
            
        Returns:
            Configured workflow instance
            
        Raises:
            ValueError: If workflow type is unsupported
            RuntimeError: If workflow creation fails
        """
        try:
            # Determine workflow type
            target_type = workflow_type or getattr(settings, 'workflow_type', 'sequential')
            
            # Validate and normalize workflow type
            workflow_enum = cls._validate_workflow_type(target_type)
            
            # Get workflow class
            workflow_class = cls._workflow_registry[workflow_enum]
            
            logger.info(f"Creating {workflow_enum.value} workflow")
            
            # Create and return workflow instance
            workflow = workflow_class(
                alpaca_api=alpaca_api,
                tiingo_api=tiingo_api,
                telegram_bot=telegram_bot
            )
            
            logger.info(f"Successfully created {workflow_enum.value} workflow")
            return workflow
            
        except Exception as e:
            logger.error(f"Failed to create workflow: {e}")
            raise RuntimeError(f"Workflow creation failed: {e}") from e
    
    @classmethod
    def _validate_workflow_type(cls, workflow_type: Optional[str]) -> WorkflowType:
        """
        Validate and convert workflow type string to enum.
        
        Args:
            workflow_type: String representation of workflow type
            
        Returns:
            Validated WorkflowType enum
            
        Raises:
            ValueError: If workflow type is unsupported
        """
        if workflow_type is None:
            return WorkflowType.SEQUENTIAL  # Default fallback
            
        try:
            return WorkflowType(workflow_type.lower())
        except ValueError:
            available_types = [wt.value for wt in WorkflowType]
            raise ValueError(
                f"Unsupported workflow type: {workflow_type}. "
                f"Available types: {available_types}"
            )
    
    @classmethod
    def get_available_workflows(cls) -> Dict[str, Dict[str, Any]]:
        """
        Get information about available workflow types.
        
        Returns:
            Dictionary containing workflow information
        """
        workflows = {}
        
        for workflow_type, workflow_class in cls._workflow_registry.items():
            workflows[workflow_type.value] = {
                "name": workflow_type.value.title().replace('_', ' '),
                "class": workflow_class.__name__,
                "description": workflow_class.__doc__.strip().split('\n')[0] if workflow_class.__doc__ else "No description",
                "module": workflow_class.__module__
            }
        
        return workflows
    
    @classmethod
    def register_workflow(cls, workflow_type: WorkflowType, workflow_class: Type[WorkflowBase]):
        """
        Register a new workflow type.
        
        Args:
            workflow_type: Type of workflow to register
            workflow_class: Workflow class implementation
            
        Raises:
            TypeError: If workflow_class doesn't inherit from WorkflowBase
        """
        if not issubclass(workflow_class, WorkflowBase):
            raise TypeError(f"Workflow class {workflow_class} must inherit from WorkflowBase")
        
        cls._workflow_registry[workflow_type] = workflow_class
        logger.info(f"Registered new workflow type: {workflow_type.value}")
    
    @classmethod
    def is_workflow_supported(cls, workflow_type: str) -> bool:
        """
        Check if a workflow type is supported.
        
        Args:
            workflow_type: Workflow type to check
            
        Returns:
            True if supported, False otherwise
        """
        try:
            cls._validate_workflow_type(workflow_type)
            return True
        except ValueError:
            return False
    
    @classmethod
    def get_default_workflow_type(cls) -> str:
        """
        Get the default workflow type from configuration.
        
        Returns:
            Default workflow type string
        """
        workflow_type = getattr(settings, 'workflow_type', 'sequential')
        return workflow_type if workflow_type is not None else 'sequential'
    
    @classmethod
    def validate_configuration(cls) -> Dict[str, Any]:
        """
        Validate the current workflow configuration.
        
        Returns:
            Dictionary containing validation results
        """
        validation_result = {
            "valid": True,
            "errors": [],
            "warnings": [],
            "config": {}
        }
        
        try:
            # Check workflow type setting
            configured_type = getattr(settings, 'workflow_type', None)
            
            if configured_type is None:
                validation_result["warnings"].append("No workflow_type configured, using default: sequential")
                configured_type = "sequential"
            
            # Validate configured type
            if not cls.is_workflow_supported(configured_type):
                available_types = [wt.value for wt in WorkflowType]
                validation_result["errors"].append(
                    f"Unsupported workflow type: {configured_type}. Available: {available_types}"
                )
                validation_result["valid"] = False
            
            validation_result["config"]["workflow_type"] = configured_type
            
            # Check LLM provider compatibility
            llm_provider = getattr(settings, 'llm_provider', 'openai')
            validation_result["config"]["llm_provider"] = llm_provider
            
            if configured_type == "tool_calling" and llm_provider.lower() not in ["openai", "deepseek"]:
                validation_result["warnings"].append(
                    f"Tool calling workflow works best with OpenAI or DeepSeek. "
                    f"Current provider: {llm_provider}"
                )
            
            # Check required API keys
            required_keys = []
            if llm_provider.lower() == "openai":
                required_keys.append("openai_api_key")
            elif llm_provider.lower() == "deepseek":
                required_keys.append("deepseek_api_key")
            
            for key in required_keys:
                if not getattr(settings, key, None):
                    validation_result["errors"].append(f"Missing required configuration: {key}")
                    validation_result["valid"] = False
            
        except Exception as e:
            validation_result["errors"].append(f"Configuration validation error: {e}")
            validation_result["valid"] = False
        
        return validation_result
    
    @classmethod
    def create_workflow_info(cls, workflow_type: str) -> Dict[str, Any]:
        """
        Get detailed information about a specific workflow type.
        
        Args:
            workflow_type: Type of workflow to get info for
            
        Returns:
            Dictionary containing workflow information
        """
        try:
            workflow_enum = cls._validate_workflow_type(workflow_type)
            workflow_class = cls._workflow_registry[workflow_enum]
            
            info = {
                "type": workflow_enum.value,
                "name": workflow_enum.value.title().replace('_', ' '),
                "class_name": workflow_class.__name__,
                "module": workflow_class.__module__,
                "description": workflow_class.__doc__.strip() if workflow_class.__doc__ else "No description",
                "supported": True
            }
            
            # Add specific features based on workflow type
            if workflow_enum == WorkflowType.SEQUENTIAL:
                info["features"] = [
                    "Fixed execution sequence",
                    "Predictable workflow steps",
                    "LangGraph state management",
                    "Structured analysis pipeline"
                ]
                info["best_for"] = "Consistent, repeatable trading analysis"
                
            elif workflow_enum == WorkflowType.TOOL_CALLING:
                info["features"] = [
                    "Dynamic tool selection",
                    "LLM-driven decision making",
                    "Flexible execution order",
                    "Real-time tool calling"
                ]
                info["best_for"] = "Adaptive, intelligent trading analysis"
            
            return info
            
        except ValueError as e:
            return {
                "type": workflow_type,
                "supported": False,
                "error": str(e)
            }


# Convenience functions for common operations

def create_default_workflow(alpaca_api: AlpacaAPI, tiingo_api: TiingoAPI, telegram_bot=None) -> WorkflowBase:
    """
    Create a workflow using the default configuration.
    
    Args:
        alpaca_api: Alpaca API client
        tiingo_api: Tiingo API client
        telegram_bot: Optional Telegram bot instance
        
    Returns:
        Configured workflow instance
    """
    return WorkflowFactory.create_workflow(alpaca_api, tiingo_api, telegram_bot)


def get_workflow_choices() -> list[str]:
    """
    Get a list of available workflow type choices.
    
    Returns:
        List of available workflow type strings
    """
    return [wt.value for wt in WorkflowType]


def validate_workflow_config() -> bool:
    """
    Quick validation of workflow configuration.
    
    Returns:
        True if configuration is valid, False otherwise
    """
    result = WorkflowFactory.validate_configuration()
    if not result["valid"]:
        for error in result["errors"]:
            logger.error(f"Configuration error: {error}")
    
    for warning in result["warnings"]:
        logger.warning(f"Configuration warning: {warning}")
    
    return result["valid"] 