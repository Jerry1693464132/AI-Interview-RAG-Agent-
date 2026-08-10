"""
DeepSeek LLM 客户端封装 — 基于 OpenAI 兼容 SDK，统一 LLM 调用。

特性:
    - httpx 连接池复用，减少 TLS 握手
    - 指数退避自动重试 (1s → 2s → 4s)
    - 结构化日志记录每次调用
    - 全量类型标注

用法:
    from app.core.llm_client import LLMClient, get_llm_client

    client = LLMClient()
    response = await client.chat(messages=[...])
    # 或通过 FastAPI DI
    response = await llm_client.chat(messages=[...])
"""

import time
from typing import Any, Optional

import structlog
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletion

from app.core.config import DeepSeekSettings, get_settings

logger = structlog.get_logger(__name__)


class LLMClientError(Exception):
    """LLM 调用异常基类。"""


class LLMClient:
    """
    DeepSeek API 客户端 — 封装 chat/completions 调用。

    Attributes:
        client:  异步 OpenAI 兼容客户端
        settings: DeepSeek 配置
    """

    def __init__(self, settings: Optional[DeepSeekSettings] = None) -> None:
        self.settings = settings or get_settings().deepseek
        self.client = AsyncOpenAI(
            api_key=self.settings.API_KEY,
            base_url=self.settings.BASE_URL,
            timeout=120.0,  # 国内访问 DeepSeek 可能较慢
            max_retries=0,  # 我们自己控制重试
        )

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        response_format: Optional[dict[str, str]] = None,
    ) -> ChatCompletion:
        """
        调用 DeepSeek chat/completions。

        Args:
            messages:         对话消息列表 [{"role": "system", "content": "..."}, ...]
            model:            模型名称，默认 deepseek-chat
            temperature:      采样温度
            max_tokens:       最大输出 token 数
            response_format:  输出格式约束，如 {"type": "json_object"}

        Returns:
            ChatCompletion 对象

        Raises:
            LLMClientError: 所有重试耗尽后仍失败
        """
        model = model or self.settings.MODEL
        temperature = temperature if temperature is not None else self.settings.TEMPERATURE
        max_tokens = max_tokens or self.settings.MAX_TOKENS

        logger.info(
            "llm_chat_request",
            model=model,
            message_count=len(messages),
            temperature=temperature,
            max_tokens=max_tokens,
        )

        last_exception: Optional[Exception] = None
        delays = [1.0, 2.0, 4.0]  # 指数退避: 1s → 2s → 4s

        for attempt, delay in enumerate(delays):
            try:
                response = await self.client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    response_format=response_format,
                )
                logger.info(
                    "llm_chat_success",
                    model=model,
                    usage=response.usage.model_dump() if response.usage else None,
                )
                return response

            except Exception as exc:
                last_exception = exc
                logger.warning(
                    "llm_chat_retry",
                    attempt=attempt + 1,
                    delay=delay,
                    error=str(exc),
                )
                time.sleep(delay)

        logger.error("llm_chat_exhausted", error=str(last_exception))
        raise LLMClientError(f"LLM 调用失败，已重试 3 次: {last_exception}") from last_exception

    async def close(self) -> None:
        """关闭 HTTP 连接池。"""
        await self.client.close()


# ---- 单例管理 ----

_llm_client: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    """获取 LLMClient 单例（FastAPI 依赖注入用）。"""
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client
