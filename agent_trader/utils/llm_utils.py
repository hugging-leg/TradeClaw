"""
LLM 工具函数

统一使用 OpenAI 兼容格式，通过 base_url 支持各种 API。

包含针对非标准 OpenAI 兼容 provider 的兼容性修复：
- FixedIndexChatOpenAI: 修复某些 provider 在流式返回多个 tool calls 时
  所有 tool_call chunk 的 index 都为 0 的问题。LangChain 按 index 聚合
  chunk，如果 index 全为 0 则会把多个 tool call 的 name/id/args 拼接在一起，
  导致 "get_weatherget_time" 这种无效工具名。
- Reasoning model 兼容：
  1. 流式输出：从 API delta 中提取 reasoning_content 并存入
     AIMessageChunk.additional_kwargs，使上层能实时展示思考过程。
  2. 多轮对话：自动为 assistant 消息补上 reasoning_content 字段，
     满足 DeepSeek thinking mode 等 API 要求。
"""

from agent_trader.utils.logging_config import get_logger
from typing import Optional, Any, Iterator, AsyncIterator

from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk

from config import settings

logger = get_logger(__name__)


# ============================================================
# Reasoning content 相关常量
# ============================================================

# API delta 中可能携带 reasoning 内容的字段名（不同 provider 使用不同的字段名）
# - reasoning_content: DeepSeek 官方 API
# - reasoning: OpenRouter 代理 DeepSeek / 部分第三方 API
_REASONING_DELTA_KEYS = ("reasoning_content", "reasoning")

# 需要在多轮对话中回传 reasoning_content 的模型名关键词（小写匹配）
# DeepSeek Reasoner 要求所有历史 assistant 消息必须包含 reasoning_content
_REASONING_REQUIRED_MODEL_KEYWORDS = ("reasoner",)


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
    ChatOpenAI 子类，包含多项兼容性修复：

    1. 流式 tool_call_chunks index 修正：
       某些 OpenAI 兼容 API 代理在流式返回并行 tool calls 时，所有 tool_call
       chunk 的 index 都为 0（不符合 OpenAI 规范）。这会导致 LangChain 在聚合
       AIMessageChunk 时将多个 tool call 的 name、id、args 拼接在一起。
       此子类在 _stream/_astream 阶段拦截每个 chunk，通过有状态的
       _ToolCallIndexFixer 检测并修正 index。
       对于正常的 provider（index 已正确），此修复不会产生副作用。

    2. 流式 reasoning_content 提取：
       Reasoning model（如 deepseek-reasoner）在流式 delta 中返回 reasoning_content
       字段，但 ChatOpenAI 的 _convert_delta_to_message_chunk 不提取此字段。
       此子类 override _convert_chunk_to_generation_chunk，将 delta 中的
       reasoning_content 存入 AIMessageChunk.additional_kwargs["reasoning_content"]，
       使上层（workflow_base）能实时推送思考过程到前端。
       对于不返回 reasoning_content 的模型无副作用。

    3. 多轮对话 reasoning_content 回传：
       某些 reasoning model（如 deepseek-reasoner）在多轮对话中要求 assistant
       消息必须包含 reasoning_content 字段。LangChain 的 _convert_message_to_dict
       不会从 AIMessage.additional_kwargs 中提取此字段。此子类 override
       _get_request_payload，自动将 reasoning_content 注入到 API 请求的
       assistant 消息中。对于不需要此字段的模型无副作用。
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

    def _convert_chunk_to_generation_chunk(
        self,
        chunk: dict,
        default_chunk_class: type,
        base_generation_info: dict | None,
    ) -> ChatGenerationChunk | None:
        """
        Override 父类方法，从流式 delta 中提取 reasoning_content。

        ChatOpenAI 的 _convert_delta_to_message_chunk 只提取 content、tool_calls
        等标准字段，不处理 reasoning_content。Reasoning model（如 deepseek-reasoner、
        通过 OpenRouter 的 DeepSeek R1 等）在 delta 中返回的 reasoning_content
        会被丢弃。

        此 override 在父类处理完后，检查原始 delta 中是否有 reasoning 相关字段，
        如果有则存入 AIMessageChunk.additional_kwargs["reasoning_content"]。
        """
        generation_chunk = super()._convert_chunk_to_generation_chunk(
            chunk, default_chunk_class, base_generation_info,
        )
        if generation_chunk is None:
            return None

        # 从原始 chunk 中提取 reasoning content
        choices = chunk.get("choices") or chunk.get("chunk", {}).get("choices") or []
        if choices and isinstance(generation_chunk.message, AIMessageChunk):
            delta = choices[0].get("delta") or {}
            for key in _REASONING_DELTA_KEYS:
                reasoning_text = delta.get(key)
                if reasoning_text is not None:
                    generation_chunk.message.additional_kwargs["reasoning_content"] = (
                        reasoning_text
                    )
                    break

        return generation_chunk

    def _get_request_payload(
        self,
        input_: Any,
        *,
        stop: Any = None,
        **kwargs: Any,
    ) -> dict:
        """
        构建 API 请求 payload，并为需要 reasoning_content 的模型补上该字段。

        某些 reasoning model（如 deepseek-reasoner）要求多轮对话中**所有**历史
        assistant 消息必须包含 reasoning_content 字段，否则 API 返回 400。

        常见触发场景：
        - 从普通模型切换到 reasoning model 后，checkpointer 中保存的旧 assistant
          消息没有 reasoning_content
        - LangChain 的 _convert_message_to_dict 不会从 AIMessage.additional_kwargs
          中提取 reasoning_content

        修复策略：
        1. 先调用父类构建标准 payload
        2. 检测当前模型是否需要 reasoning_content
        3. 如果是，为所有 assistant 消息注入 reasoning_content：
           - 优先使用 AIMessage.additional_kwargs 中保存的值
           - 如果没有（如旧消息），补空字符串 ""
        """
        # 获取原始 LangChain 消息（用于提取 reasoning_content）
        messages = self._convert_input(input_).to_messages()

        # 构建标准 payload
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)

        # 检测当前模型是否需要 reasoning_content 回传
        model_name = (payload.get("model") or getattr(self, "model_name", "") or "").lower()
        needs_reasoning_content = any(
            kw in model_name for kw in _REASONING_REQUIRED_MODEL_KEYWORDS
        )

        if needs_reasoning_content and "messages" in payload:
            for i, msg_dict in enumerate(payload["messages"]):
                if msg_dict.get("role") == "assistant":
                    if "reasoning_content" not in msg_dict:
                        # 优先从原始 AIMessage 的 additional_kwargs 提取
                        reasoning = ""
                        if i < len(messages) and isinstance(messages[i], AIMessage):
                            reasoning = messages[i].additional_kwargs.get(
                                "reasoning_content", ""
                            ) or ""
                        msg_dict["reasoning_content"] = reasoning

        return payload


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
