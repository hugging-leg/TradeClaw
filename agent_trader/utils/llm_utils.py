"""
LLM 工具函数

统一使用 OpenAI 兼容格式，通过 base_url 支持各种 API。

包含针对非标准 OpenAI 兼容 provider 的兼容性修复：
- FixedIndexChatOpenAI: 修复某些 provider 在流式返回多个 tool calls 时
  所有 tool_call chunk 的 index 都为 0 的问题。LangChain 按 index 聚合
  chunk，如果 index 全为 0 则会把多个 tool call 的 name/id/args 拼接在一起，
  导致 "get_weatherget_time" 这种无效工具名。
"""

from agent_trader.utils.logging_config import get_logger
from typing import Optional, Any, Iterator, AsyncIterator

from langchain_openai import ChatOpenAI
from langchain_core.outputs import ChatGenerationChunk

from config import settings

logger = get_logger(__name__)


# ============================================================
# 兼容性修复: tool_call_chunks index 纠正
# ============================================================

class _ToolCallIndexFixer:
    """
    有状态的 tool_call_chunk index 修复器。

    某些 OpenAI 兼容 provider（如 new-api 代理 Gemini）在流式返回多个
    parallel tool calls 时，所有 chunk 的 index 都为 0。LangChain 的
    AIMessageChunk.__add__ 按 index 聚合，导致 name/id/args 被错误拼接
    （如 "get_weatherget_time"）。

    修复策略：
    - 跟踪已见过的 tool_call_id → index 映射
    - 当遇到新的 tool_call_id 但 index=0 时，分配递增的 index
    - 无 id 的续传 chunk（args 补充）保持 index 不变
    - 对于正常 provider（index 已正确），此修复不会产生副作用
    """

    def __init__(self):
        self._id_to_index: dict[str, int] = {}
        self._next_index: int = 0

    def fix(self, chunk: ChatGenerationChunk) -> ChatGenerationChunk:
        msg = chunk.message
        tc_chunks = getattr(msg, "tool_call_chunks", None)
        if not tc_chunks:
            return chunk

        for tc in tc_chunks:
            tc_id = tc.get("id")
            tc_name = tc.get("name")

            if tc_id:
                if tc_id in self._id_to_index:
                    # 已知 id — 使用之前分配的 index
                    tc["index"] = self._id_to_index[tc_id]
                else:
                    # 新 id — 检查是否需要修正
                    # 如果这是第一个 tool call 且 index=0，正常
                    # 如果 index=0 但已经有其他 tool call，需要修正
                    current_index = tc.get("index", 0)
                    if current_index == 0 and self._next_index > 0:
                        # 需要修正：分配新 index
                        tc["index"] = self._next_index
                        self._id_to_index[tc_id] = self._next_index
                        self._next_index += 1
                    else:
                        # 正常情况或第一个 tool call
                        self._id_to_index[tc_id] = current_index
                        self._next_index = max(self._next_index, current_index + 1)
            elif tc_name:
                # 有 name 但没有 id — 某些 provider 的边缘情况
                # 按新 tool call 处理
                tc["index"] = self._next_index
                self._next_index += 1
            # else: 无 id 无 name 的续传 chunk（只有 args），保持 index 不变

        return chunk


class FixedIndexChatOpenAI(ChatOpenAI):
    """
    ChatOpenAI 子类，修复流式 tool_call_chunks 的 index 问题。

    某些 OpenAI 兼容 API 代理在流式返回并行 tool calls 时，所有 tool_call
    chunk 的 index 都为 0（不符合 OpenAI 规范）。这会导致 LangChain 在聚合
    AIMessageChunk 时将多个 tool call 的 name、id、args 拼接在一起。

    此子类在 _stream/_astream 阶段拦截每个 chunk，通过有状态的
    _ToolCallIndexFixer 检测并修正 index。
    对于正常的 provider（index 已正确），此修复不会产生副作用。
    """

    def _stream(self, *args: Any, **kwargs: Any) -> Iterator[ChatGenerationChunk]:
        fixer = _ToolCallIndexFixer()
        for chunk in super()._stream(*args, **kwargs):
            yield fixer.fix(chunk)

    async def _astream(
        self, *args: Any, **kwargs: Any
    ) -> AsyncIterator[ChatGenerationChunk]:
        fixer = _ToolCallIndexFixer()
        async for chunk in super()._astream(*args, **kwargs):
            yield fixer.fix(chunk)


# ============================================================
# LLM 客户端工厂
# ============================================================

def create_llm_client(
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0.1,
    **kwargs
) -> FixedIndexChatOpenAI:
    """
    创建 LLM 客户端（OpenAI 兼容格式）

    使用 FixedIndexChatOpenAI 以兼容 tool_call index 不规范的 provider。

    Args:
        base_url: API base URL，默认从配置读取
        api_key: API key，默认从配置读取
        model: 模型名称，默认从配置读取
        temperature: 温度参数，默认 0.1
        **kwargs: 其他参数传递给 ChatOpenAI

    Returns:
        FixedIndexChatOpenAI 实例

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
    return FixedIndexChatOpenAI(
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
