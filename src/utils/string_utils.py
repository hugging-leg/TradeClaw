"""
General string processing utilities.

This module contains common string manipulation functions used throughout the system.
"""

import re
from typing import Optional


def safe_format_text(text: str, max_length: Optional[int] = None, allow_markdown: bool = False) -> str:
    """
    Safely format text with minimal processing.
    
    Args:
        text: Text to format
        max_length: Maximum length to truncate to
        allow_markdown: Whether to preserve Markdown formatting
        
    Returns:
        Text with minimal escaping for compatibility
    """
    if not text:
        return ""
    
    # Convert to string if not already
    text = str(text)
    
    if allow_markdown:
        # For Markdown mode, do minimal processing
        # Only escape problematic characters that commonly cause parsing errors
        escaped = text.replace('\\', '\\\\')  # Escape backslashes
        # That's it! Keep it simple like the old code
    else:
        # Only when explicitly not allowing markdown, escape the formatting characters
        escaped = text.replace('\\', '\\\\')
        escaped = escaped.replace('*', '\\*')
        escaped = escaped.replace('_', '\\_')
        escaped = escaped.replace('[', '\\[')
        escaped = escaped.replace('`', '\\`')
    
    # Truncate if specified
    if max_length and len(escaped) > max_length:
        escaped = escaped[:max_length - 3] + "..."
    
    return escaped


def clean_text(text: str, remove_extra_whitespace: bool = True) -> str:
    """
    Clean text by removing unwanted characters and formatting.
    
    Args:
        text: Text to clean
        remove_extra_whitespace: Whether to remove extra whitespace
        
    Returns:
        Cleaned text
    """
    if not text:
        return ""
    
    text = str(text)
    
    # Remove control characters except newlines and tabs
    text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', text)
    
    if remove_extra_whitespace:
        # Remove excessive newlines
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        # Remove excessive spaces
        text = re.sub(r' {2,}', ' ', text)
        
        # Remove leading/trailing whitespace from each line
        lines = text.split('\n')
        text = '\n'.join(line.strip() for line in lines)
    
    return text.strip()


def truncate_text(text: str, max_length: int, suffix: str = "...") -> str:
    """
    Truncate text to maximum length with optional suffix.
    
    Args:
        text: Text to truncate
        max_length: Maximum allowed length
        suffix: Suffix to add when truncating
        
    Returns:
        Truncated text
    """
    if not text or max_length <= 0:
        return ""
    
    text = str(text)
    
    if len(text) <= max_length:
        return text
    
    # Calculate effective length considering suffix
    effective_length = max_length - len(suffix)
    if effective_length <= 0:
        return suffix[:max_length]
    
    return text[:effective_length] + suffix


def escape_special_chars(text: str, chars_to_escape: str = "*_[]()~`") -> str:
    """
    Escape special characters in text.
    
    Args:
        text: Text to escape
        chars_to_escape: Characters that need escaping
        
    Returns:
        Text with escaped characters
    """
    if not text:
        return ""
    
    escaped = str(text)
    for char in chars_to_escape:
        escaped = escaped.replace(char, f'\\{char}')
    
    return escaped


def normalize_symbol(symbol: str) -> str:
    """
    Normalize trading symbol for consistent display.
    
    Args:
        symbol: Trading symbol to normalize
        
    Returns:
        Normalized symbol
    """
    if not symbol:
        return ""
    
    # Convert to uppercase and strip whitespace
    symbol = str(symbol).upper().strip()
    
    # Replace common separators with underscores
    symbol = re.sub(r'[-\s]+', '_', symbol)
    
    return symbol


def extract_numbers(text: str) -> list:
    """
    Extract all numbers from text.
    
    Args:
        text: Text to extract numbers from
        
    Returns:
        List of numbers found in text
    """
    if not text:
        return []
    
    # Find all numbers (including decimals)
    pattern = r'-?\d+(?:\.\d+)?'
    matches = re.findall(pattern, str(text))
    
    # Convert to appropriate numeric types
    numbers = []
    for match in matches:
        try:
            if '.' in match:
                numbers.append(float(match))
            else:
                numbers.append(int(match))
        except ValueError:
            continue
    
    return numbers


def format_currency(amount: float, currency: str = "$", decimal_places: int = 2) -> str:
    """
    Format amount as currency string.
    
    Args:
        amount: Amount to format
        currency: Currency symbol
        decimal_places: Number of decimal places
        
    Returns:
        Formatted currency string
    """
    try:
        amount = float(amount)
        formatted = f"{currency}{amount:,.{decimal_places}f}"
        return formatted
    except (ValueError, TypeError):
        return f"{currency}0.00"


def format_percentage(value: float, decimal_places: int = 2) -> str:
    """
    Format value as percentage string.
    
    Args:
        value: Value to format (0.1 = 10%)
        decimal_places: Number of decimal places
        
    Returns:
        Formatted percentage string
    """
    try:
        value = float(value)
        percentage = value * 100
        return f"{percentage:.{decimal_places}f}%"
    except (ValueError, TypeError):
        return "0.00%"


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename by removing invalid characters.
    
    Args:
        filename: Filename to sanitize
        
    Returns:
        Sanitized filename
    """
    if not filename:
        return "unnamed"
    
    # Remove invalid filename characters
    sanitized = re.sub(r'[<>:"/\\|?*]', '_', str(filename))
    
    # Remove control characters
    sanitized = re.sub(r'[\x00-\x1F\x7F]', '', sanitized)
    
    # Limit length
    sanitized = sanitized[:255]
    
    # Ensure it's not empty
    if not sanitized or sanitized.isspace():
        return "unnamed"
    
    return sanitized.strip() 