"""
Abstract message transport interface for low-level message delivery.

This module defines the abstract interface for message transport implementations,
focusing purely on message delivery without business logic.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from enum import Enum


class MessageFormat(Enum):
    """Supported message formats"""
    PLAIN_TEXT = "plain_text"
    MARKDOWN = "markdown" 
    HTML = "html"
    JSON = "json"


class MessageTransport(ABC):
    """
    Abstract base class for message transport implementations.
    
    This interface is focused purely on message delivery mechanics,
    without any business logic or message formatting concerns.
    """
    
    @abstractmethod
    async def send_raw_message(self, 
                              content: str, 
                              format_type: MessageFormat = MessageFormat.PLAIN_TEXT,
                              **kwargs) -> bool:
        """
        Send a raw message.
        
        Args:
            content: Raw message content
            format_type: Message format (plain_text, markdown, html, json)
            **kwargs: Transport-specific parameters
            
        Returns:
            True if message was sent successfully, False otherwise
        """
        pass
    
    @abstractmethod
    async def initialize(self) -> bool:
        """
        Initialize the transport service.
        
        Returns:
            True if initialization successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def start(self) -> bool:
        """
        Start the transport service.
        
        Returns:
            True if start successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def stop(self) -> bool:
        """
        Stop the transport service.
        
        Returns:
            True if stop successful, False otherwise
        """
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """
        Check if the transport is available and ready to send messages.
        
        Returns:
            True if available, False otherwise
        """
        pass
    
    @abstractmethod
    def get_transport_name(self) -> str:
        """
        Get the name of the transport provider.
        
        Returns:
            String name of the transport (e.g., "Telegram", "Discord", "SMTP")
        """
        pass
    
    @abstractmethod
    def get_transport_info(self) -> Dict[str, Any]:
        """
        Get detailed information about the transport provider.
        
        Returns:
            Dictionary containing transport information, capabilities, etc.
        """
        pass
    
    @abstractmethod
    def get_rate_limits(self) -> Dict[str, Any]:
        """
        Get rate limit information for this transport.
        
        Returns:
            Dictionary containing rate limit information
        """
        pass 