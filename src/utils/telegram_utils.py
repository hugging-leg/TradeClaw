"""
Telegram-specific string processing utilities.

This module contains functions for handling Telegram message formatting,
Markdown processing, and content cleaning.
"""

import re
from src.utils.logging_config import get_logger
from typing import Optional

logger = get_logger(__name__)


def escape_markdown_symbols(text: str, symbols: str = "_") -> str:
    """
    Escape Markdown symbols that might cause parsing issues.
    
    Args:
        text: Text to escape
        symbols: Symbols to escape (default: underscores for trading symbols)
        
    Returns:
        Text with escaped symbols
    """
    if not text:
        return ""
    
    escaped = str(text)
    for symbol in symbols:
        escaped = escaped.replace(symbol, f'\\{symbol}')
    
    return escaped


def fix_markdown_issues(content: str) -> str:
    """
    Attempt to fix common Markdown parsing issues in Telegram messages.
    
    Args:
        content: Original content with potential Markdown issues
        
    Returns:
        Content with common Markdown issues fixed
    """
    if not content:
        return content
    
    fixed = content
    
    # Fix unmatched bold markers
    bold_count = fixed.count('**')
    if bold_count % 2 == 1:
        # Add closing bold marker at the end
        fixed += '**'
    
    # Fix unmatched italic markers - but be careful not to escape underscores in command names
    # Only escape underscores that are likely to be markdown formatting, not part of text
    italic_count = fixed.count('_')
    if italic_count % 2 == 1:
        # Check if the unmatched underscore is part of a command or normal text
        last_underscore = fixed.rfind('_')
        if last_underscore != -1:
            # Check if it's part of a command like /emergency_stop
            is_command_part = False
            start = max(0, last_underscore - 20)
            end = min(len(fixed), last_underscore + 20)
            context = fixed[start:end]
            if '/' in context and context.find('/') < context.find('_'):
                is_command_part = True
            
            # Only escape if it's not part of a command
            if not is_command_part:
                fixed = fixed[:last_underscore] + '\\_' + fixed[last_underscore + 1:]
    
    # Fix unmatched brackets
    open_brackets = fixed.count('[')
    close_brackets = fixed.count(']')
    if open_brackets != close_brackets:
        # Escape all brackets to be safe
        fixed = fixed.replace('[', '\\[').replace(']', '\\]')
    
    # Find and fix incomplete links
    incomplete_links = re.findall(r'\[([^\]]*)\]\(([^)]*$)', fixed)
    for text, incomplete_url in incomplete_links:
        # Remove the incomplete link formatting
        pattern = f'\\[{re.escape(text)}\\]\\({re.escape(incomplete_url)}'
        replacement = f'{text} ({incomplete_url})'
        fixed = re.sub(pattern, replacement, fixed)
    
    # Fix common problematic character sequences
    # Escape backslashes that aren't already escaped
    fixed = re.sub(r'(?<!\\)\\(?!\\)', r'\\\\', fixed)
    
    # Fix multiple consecutive formatting characters
    fixed = re.sub(r'\*{3,}', '*', fixed)  # Replace *** with *
    fixed = re.sub(r'_{3,}', '_', fixed)    # Replace ___ with _
    
    # Final cleanup
    fixed = fixed.strip()
    
    return fixed


def clean_content_for_telegram(content: str) -> str:
    """
    Clean content for Telegram by removing problematic characters.
    
    Args:
        content: Original content
        
    Returns:
        Cleaned content safe for Telegram
    """
    if not content:
        return ""
    
    # Remove all Markdown formatting
    cleaned = content.replace('**', '')
    cleaned = cleaned.replace('*', '')
    cleaned = cleaned.replace('__', '')
    cleaned = cleaned.replace('_', '')
    cleaned = cleaned.replace('`', '')
    cleaned = cleaned.replace('~', '')
    cleaned = cleaned.replace('[', '')
    cleaned = cleaned.replace(']', '')
    cleaned = cleaned.replace('(', '')
    cleaned = cleaned.replace(')', '')
    
    # Remove excessive newlines
    cleaned = cleaned.replace('\n\n\n', '\n\n')
    
    # Remove leading/trailing whitespace
    cleaned = cleaned.strip()
    
    # If still too long, truncate
    if len(cleaned) > 4000:
        cleaned = cleaned[:4000] + "... (truncated)"
    
    return cleaned


def is_valid_telegram_message(content: str) -> bool:
    """
    Check if content is likely to be valid for Telegram.
    
    Args:
        content: Content to validate
        
    Returns:
        True if content appears valid for Telegram
    """
    if not content:
        return False
    
    content = str(content)
    
    # Check length
    if len(content) > 4096:
        return False
    
    # Check for balanced markdown
    if content.count('*') % 2 != 0:
        return False
    
    if content.count('_') % 2 != 0:
        # Allow unescaped underscores in commands
        if not any(f'/{word}' in content for word in content.split() if '_' in word):
            return False
    
    if content.count('[') != content.count(']'):
        return False
    
    if content.count('(') != content.count(')'):
        return False
    
    return True


def escape_telegram_symbols(text: str, preserve_commands: bool = True) -> str:
    """
    Escape symbols that might cause Telegram parsing issues.
    
    Args:
        text: Text to escape
        preserve_commands: Whether to preserve command formatting (e.g., /command_name)
        
    Returns:
        Text with escaped symbols
    """
    if not text:
        return ""
    
    escaped = str(text)
    
    if preserve_commands:
        # Find all commands and temporarily replace them
        commands = re.findall(r'/\w+(?:_\w+)*', escaped)
        command_placeholders = {}
        
        for i, cmd in enumerate(commands):
            placeholder = f"__CMD_PLACEHOLDER_{i}__"
            command_placeholders[placeholder] = cmd
            escaped = escaped.replace(cmd, placeholder, 1)
    
    # Escape problematic characters
    escaped = escaped.replace('_', '\\_')
    escaped = escaped.replace('*', '\\*')
    escaped = escaped.replace('[', '\\[')
    escaped = escaped.replace(']', '\\]')
    escaped = escaped.replace('(', '\\(')
    escaped = escaped.replace(')', '\\)')
    escaped = escaped.replace('`', '\\`')
    
    if preserve_commands:
        # Restore commands
        for placeholder, cmd in command_placeholders.items():
            escaped = escaped.replace(placeholder, cmd)
    
    return escaped


def format_telegram_code_block(code: str, language: str = "") -> str:
    """
    Format code block for Telegram.
    
    Args:
        code: Code content
        language: Programming language (optional)
        
    Returns:
        Formatted code block
    """
    if not code:
        return ""
    
    # Escape any existing backticks
    escaped_code = str(code).replace('`', '\\`')
    
    if language:
        return f"```{language}\n{escaped_code}\n```"
    else:
        return f"```\n{escaped_code}\n```"


def format_telegram_inline_code(code: str) -> str:
    """
    Format inline code for Telegram.
    
    Args:
        code: Code content
        
    Returns:
        Formatted inline code
    """
    if not code:
        return ""
    
    # Escape any existing backticks
    escaped_code = str(code).replace('`', '\\`')
    
    return f"`{escaped_code}`"


def extract_byte_offset_from_error(error_message: str) -> Optional[int]:
    """
    Extract byte offset from Telegram parsing error message.
    
    Args:
        error_message: Error message from Telegram
        
    Returns:
        Byte offset if found, None otherwise
    """
    try:
        if "byte offset" in error_message:
            offset_match = re.search(r'byte offset (\d+)', error_message)
            if offset_match:
                return int(offset_match.group(1))
    except Exception as e:
        logger.debug(f"Error extracting byte offset: {e}")
    
    return None


def get_problematic_content_area(content: str, byte_offset: int, context_size: int = 50) -> str:
    """
    Get the problematic area around a byte offset.
    
    Args:
        content: Original content
        byte_offset: Byte offset where error occurred
        context_size: Size of context around the offset
        
    Returns:
        Content area around the problematic offset
    """
    if not content or byte_offset < 0:
        return ""
    
    start = max(0, byte_offset - context_size)
    end = min(len(content), byte_offset + context_size)
    
    area = content[start:end]
    
    if start > 0:
        area = "..." + area
    if end < len(content):
        area = area + "..."
    
    return area


def validate_markdown_formatting(content: str) -> list:
    """
    Validate Markdown formatting and return list of issues.
    
    Args:
        content: Content to validate
        
    Returns:
        List of validation issues found
    """
    issues = []
    
    if not content:
        return issues
    
    # Check for unmatched asterisks
    if content.count('*') % 2 != 0:
        issues.append("Unmatched asterisks (*) for bold formatting")
    
    # Check for unmatched underscores (but ignore commands)
    underscore_count = content.count('_')
    command_underscores = len(re.findall(r'/\w*_\w*', content)) * content.count('_')
    if (underscore_count - command_underscores) % 2 != 0:
        issues.append("Unmatched underscores (_) for italic formatting")
    
    # Check for unmatched brackets
    if content.count('[') != content.count(']'):
        issues.append("Unmatched square brackets")
    
    if content.count('(') != content.count(')'):
        issues.append("Unmatched parentheses")
    
    # Check for incomplete links
    incomplete_links = re.findall(r'\[([^\]]*)\]\(([^)]*$)', content)
    if incomplete_links:
        issues.append(f"Incomplete links found: {len(incomplete_links)}")
    
    # Check length
    if len(content) > 4096:
        issues.append(f"Content too long: {len(content)} > 4096 characters")
    
    return issues 