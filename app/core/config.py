"""
应用配置中心 - 基于 pydantic-settings，分层管理所有环境变量。

配置层级:
    AppSettings     — 应用基础配置
    DatabaseSettings— PostgreSQL + pgvector
    RedisSettings   — Redis 缓存与 Celery broker
    DeepSeekSettings— DeepSeek LLM API
    DashScopeSettings— DashScope Embedding API
    CelerySettings  — Celery 任务队列
"""

from functools import lru_cache
from typing import Optional

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# 加载 .env 到 os.environ，所有子 Settings 自动读取
load_dotenv()


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False)

    APP_NAME: str = "AI Mock Interview System"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False
    USE_MOCK_DB: bool = False   # 无数据库时开启 mock session
    SECRET_KEY: str = "change-me"
    API_V1_PREFIX: str = "/api/v1"


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="POSTGRES_", case_sensitive=False)

    HOST: str = "localhost"
    PORT: int = 5432
    USER: str = "interview"
    PASSWORD: str = "interview_secret"
    DB: str = "interview_db"

    @property
    def url(self) -> str:
        """异步数据库连接 URL (asyncpg)"""
        return (
            f"postgresql+asyncpg://{self.USER}:{self.PASSWORD}"
            f"@{self.HOST}:{self.PORT}/{self.DB}"
        )

    @property
    def sync_url(self) -> str:
        """同步数据库连接 URL (Alembic 迁移用)"""
        return (
            f"postgresql+psycopg2://{self.USER}:{self.PASSWORD}"
            f"@{self.HOST}:{self.PORT}/{self.DB}"
        )


class RedisSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="REDIS_", case_sensitive=False)

    HOST: str = "localhost"
    PORT: int = 6379
    PASSWORD: Optional[str] = None
    DB: int = 0

    @property
    def url(self) -> str:
        base = f"redis://{self.HOST}:{self.PORT}"
        if self.PASSWORD:
            return f"redis://:{self.PASSWORD}@{self.HOST}:{self.PORT}"
        return base


class DeepSeekSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DEEPSEEK_", case_sensitive=False)

    API_KEY: str = ""   # 生产环境必须设置
    BASE_URL: str = "https://api.deepseek.com"
    MODEL: str = "deepseek-chat"
    MAX_TOKENS: int = 4096
    TEMPERATURE: float = 0.7


class DashScopeSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DASHSCOPE_", case_sensitive=False)

    API_KEY: str = ""   # 生产环境必须设置
    EMBEDDING_MODEL: str = "qwen3.7-text-embedding"
    EMBEDDING_DIMENSION: int = 1024  # Qwen3.7 支持 512/1024/2048/4096


class CelerySettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CELERY_", case_sensitive=False)

    BROKER_URL: str = "redis://localhost:6379/1"
    RESULT_BACKEND: str = "redis://localhost:6379/2"
    TASK_DEFAULT_RETRY_DELAY: int = 60
    TASK_MAX_RETRIES: int = 3
    TASK_TIME_LIMIT: int = 300
    TASK_SOFT_TIME_LIMIT: int = 240


# ---- 聚合配置 ----

class Settings(BaseSettings):
    """全局配置聚合，通过单例 `get_settings()` 访问。"""

    model_config = SettingsConfigDict(case_sensitive=False)

    app: AppSettings = Field(default_factory=AppSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    deepseek: DeepSeekSettings = Field(default_factory=DeepSeekSettings)
    dashscope: DashScopeSettings = Field(default_factory=DashScopeSettings)
    celery: CelerySettings = Field(default_factory=CelerySettings)


@lru_cache()
def get_settings() -> Settings:
    """配置单例 — 全局只加载一次 .env"""
    return Settings()
