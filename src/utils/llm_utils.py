"""
LLM 工具函数

统一使用 OpenAI 兼容格式，通过 base_url 支持各种 API。
"""

from src.utils.logging_config import get_logger
from typing import Optional, Any

from langchain_openai import ChatOpenAI

from config import settings

logger = get_logger(__name__)


def create_llm_client(
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0.1,
    **kwargs
) -> ChatOpenAI:
    """
    创建 LLM 客户端（OpenAI 兼容格式）

    Args:
        base_url: API base URL，默认从配置读取
        api_key: API key，默认从配置读取
        model: 模型名称，默认从配置读取
        temperature: 温度参数，默认 0.1
        **kwargs: 其他参数传递给 ChatOpenAI

    Returns:
        ChatOpenAI 实例

    Examples:
        # 使用默认配置（主 LLM）
        llm = create_llm_client()

        # 使用 DeepSeek
        llm = create_llm_client(
            base_url="https://api.deepseek.com/v1",
            api_key="your_key",
            model="deepseek-chat"
        )

        # 使用本地 Ollama
        llm = create_llm_client(
            base_url="http://localhost:11434/v1",
            api_key="ollama",
            model="llama3"
        )
    """
    return ChatOpenAI(
        base_url=base_url or settings.llm_base_url,
        api_key=api_key or settings.llm_api_key,
        model=model or settings.llm_model,
        temperature=temperature,
        **kwargs
    )


def create_news_llm_client(temperature: float = 0.1, **kwargs) -> ChatOpenAI:
    """
    创建新闻过滤 LLM 客户端

    使用独立配置，可用便宜模型过滤新闻。
    如果未配置，使用主 LLM。

    Args:
        temperature: 温度参数
        **kwargs: 其他参数

    Returns:
        ChatOpenAI 实例
    """
    config = settings.get_news_llm_config()

    return ChatOpenAI(
        base_url=config["base_url"],
        api_key=config["api_key"],
        model=config["model"],
        temperature=temperature,
        **kwargs
    )


def get_llm_info() -> dict:
    """获取 LLM 配置信息"""
    news_config = settings.get_news_llm_config()
    news_uses_main = (
        news_config["base_url"] == settings.llm_base_url and
        news_config["model"] == settings.llm_model
    )

    return {
        "main_llm": {
            "base_url": settings.llm_base_url,
            "model": settings.llm_model,
            "configured": settings.llm_api_key != "test_key"
        },
        "news_llm": {
            "base_url": news_config["base_url"],
            "model": news_config["model"],
            "uses_main_llm": news_uses_main,
            "configured": news_config["api_key"] != "test_key"
        }
    }
