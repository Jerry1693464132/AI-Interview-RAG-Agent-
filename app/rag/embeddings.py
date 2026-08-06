"""
DashScope Embedding 封装 — 文本向量化服务。

特性:
    - httpx 连接池复用
    - 自动分批（DashScope API 单次最多 25 条）
    - 指数退避重试
    - 结构化日志

用法:
    from app.rag.embeddings import EmbeddingClient

    client = EmbeddingClient()
    vector = await client.embed_single("Python 中 GIL 是什么？")
    vectors = await client.embed_batch(["text1", "text2", ...])
"""

import asyncio
import time
from typing import Optional

import httpx
import structlog

from app.core.config import DashScopeSettings, get_settings

logger = structlog.get_logger(__name__)

# Qwen3.7-Text-Embedding 默认输出维度（可配置 512/1024/2048/4096）
EMBEDDING_DIMENSION = 1024
# DashScope API 单次调用最大文本数
MAX_BATCH_SIZE = 25


class EmbeddingError(Exception):
    """Embedding 服务异常。"""


class EmbeddingClient:
    """
    DashScope Embedding 客户端。

    Attributes:
        settings: DashScope 配置
        _client:  httpx 异步客户端
    """

    def __init__(self, settings: Optional[DashScopeSettings] = None) -> None:
        self.settings = settings or get_settings().dashscope
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url="https://dashscope.aliyuncs.com",
                headers={
                    "Authorization": f"Bearer {self.settings.API_KEY}",
                    "Content-Type": "application/json",
                },
                timeout=httpx.Timeout(30.0),
            )
        return self._client

    async def embed_single(self, text: str) -> list[float]:
        """单文本向量化。"""
        results = await self.embed_batch([text])
        return results[0]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """
        批量文本向量化 — 自动分批处理。

        Args:
            texts: 文本列表

        Returns:
            向量列表，与输入顺序一致
        """
        if not texts:
            return []

        all_embeddings: list[list[float]] = []

        # 分批调用 DashScope API
        for i in range(0, len(texts), MAX_BATCH_SIZE):
            batch = texts[i : i + MAX_BATCH_SIZE]
            batch_embeddings = await self._embed_with_retry(batch)
            all_embeddings.extend(batch_embeddings)

        return all_embeddings

    async def _embed_with_retry(
        self, texts: list[str], max_retries: int = 3
    ) -> list[list[float]]:
        """
        单批次 Embedding 调用，含指数退避重试。
        """
        client = await self._get_client()
        last_error: Optional[Exception] = None

        for attempt in range(max_retries):
            try:
                params: dict = {"text_type": "document"}
                # Qwen3.7 支持指定输出维度
                if self.settings.EMBEDDING_DIMENSION:
                    params["dimensions"] = self.settings.EMBEDDING_DIMENSION

                response = await client.post(
                    "/api/v1/services/embeddings/text-embedding/text-embedding",
                    json={
                        "model": self.settings.EMBEDDING_MODEL,
                        "input": {"texts": texts},
                        "parameters": params,
                    },
                )
                response.raise_for_status()
                data = response.json()

                # 解析响应
                embeddings = [
                    item["embedding"]
                    for item in data["output"]["embeddings"]
                ]
                logger.debug(
                    "embedding_success",
                    batch_size=len(texts),
                    dimension=len(embeddings[0]) if embeddings else 0,
                )
                return embeddings

            except httpx.HTTPStatusError as exc:
                last_error = exc
                logger.warning(
                    "embedding_http_error",
                    attempt=attempt + 1,
                    status=exc.response.status_code,
                    error=str(exc),
                )
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "embedding_error",
                    attempt=attempt + 1,
                    error=str(exc),
                )

            if attempt < max_retries - 1:
                delay = 2**attempt  # 1s → 2s → 4s
                await asyncio.sleep(delay)

        raise EmbeddingError(
            f"Embedding 调用失败 (已重试 {max_retries} 次): {last_error}"
        ) from last_error

    async def close(self) -> None:
        """关闭 HTTP 连接池。"""
        if self._client:
            await self._client.aclose()
            self._client = None


# ---- 单例 ----

_embedding_client: Optional[EmbeddingClient] = None


def get_embedding_client() -> EmbeddingClient:
    """获取 EmbeddingClient 单例。"""
    global _embedding_client
    if _embedding_client is None:
        _embedding_client = EmbeddingClient()
    return _embedding_client
