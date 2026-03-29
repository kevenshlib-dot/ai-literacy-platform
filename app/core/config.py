from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "AI素养评测平台"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = True
    SECRET_KEY: str = "change-this"
    API_V1_PREFIX: str = "/api/v1"
    APP_TIMEZONE: str = "Asia/Shanghai"

    # PostgreSQL
    TESTING: bool = False
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "ai_literacy"
    POSTGRES_PASSWORD: str = "ai_literacy_pass"
    POSTGRES_DB: str = "ai_literacy_db"
    TEST_POSTGRES_HOST: str | None = None
    TEST_POSTGRES_PORT: int | None = None
    TEST_POSTGRES_USER: str | None = None
    TEST_POSTGRES_PASSWORD: str | None = None
    TEST_POSTGRES_DB: str = "ai_literacy_test"

    def _build_postgres_url(
        self,
        *,
        async_driver: bool,
        host: str,
        port: int,
        user: str,
        password: str,
        database: str,
    ) -> str:
        driver = "postgresql+asyncpg" if async_driver else "postgresql"
        return f"{driver}://{user}:{password}@{host}:{port}/{database}"

    @property
    def DATABASE_URL(self) -> str:
        if self.TESTING:
            return self._build_postgres_url(
                async_driver=True,
                host=self.TEST_POSTGRES_HOST or self.POSTGRES_HOST,
                port=self.TEST_POSTGRES_PORT or self.POSTGRES_PORT,
                user=self.TEST_POSTGRES_USER or self.POSTGRES_USER,
                password=self.TEST_POSTGRES_PASSWORD or self.POSTGRES_PASSWORD,
                database=self.TEST_POSTGRES_DB,
            )
        return self._build_postgres_url(
            async_driver=True,
            host=self.POSTGRES_HOST,
            port=self.POSTGRES_PORT,
            user=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD,
            database=self.POSTGRES_DB,
        )

    @property
    def SYNC_DATABASE_URL(self) -> str:
        if self.TESTING:
            return self._build_postgres_url(
                async_driver=False,
                host=self.TEST_POSTGRES_HOST or self.POSTGRES_HOST,
                port=self.TEST_POSTGRES_PORT or self.POSTGRES_PORT,
                user=self.TEST_POSTGRES_USER or self.POSTGRES_USER,
                password=self.TEST_POSTGRES_PASSWORD or self.POSTGRES_PASSWORD,
                database=self.TEST_POSTGRES_DB,
            )
        return self._build_postgres_url(
            async_driver=False,
            host=self.POSTGRES_HOST,
            port=self.POSTGRES_PORT,
            user=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD,
            database=self.POSTGRES_DB,
        )

    # Elasticsearch
    ELASTICSEARCH_HOST: str = "localhost"
    ELASTICSEARCH_PORT: int = 9200

    @property
    def ELASTICSEARCH_URL(self) -> str:
        return f"http://{self.ELASTICSEARCH_HOST}:{self.ELASTICSEARCH_PORT}"

    # Milvus
    MILVUS_HOST: str = "localhost"
    MILVUS_PORT: int = 19530

    # MinIO
    MINIO_HOST: str = "localhost"
    MINIO_PORT: int = 9000
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "ai-literacy"

    @property
    def MINIO_ENDPOINT(self) -> str:
        return f"{self.MINIO_HOST}:{self.MINIO_PORT}"

    # RabbitMQ
    RABBITMQ_HOST: str = "localhost"
    RABBITMQ_PORT: int = 5672
    RABBITMQ_USER: str = "guest"
    RABBITMQ_PASSWORD: str = "guest"

    @property
    def RABBITMQ_URL(self) -> str:
        return (
            f"amqp://{self.RABBITMQ_USER}:{self.RABBITMQ_PASSWORD}"
            f"@{self.RABBITMQ_HOST}:{self.RABBITMQ_PORT}//"
        )

    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379

    @property
    def REDIS_URL(self) -> str:
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/0"

    # LLM (vLLM local server)
    LLM_API_KEY: str = "token-not-needed"
    LLM_BASE_URL: str = "http://localhost:8100/v1"
    LLM_MODEL: str = "Qwen/Qwen3.5-35B-A3B"
    GEMINI_API_KEY: str = ""
    GEMINI_BASE_URL: str = ""
    DASHSCOPE_API_KEY: str = ""
    DASHSCOPE_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    VOLCES_API_KEY: str = ""
    VOLCES_BASE_URL: str = "https://ark.cn-beijing.volces.com/api/v3"
    LOCAL_QWEN_API_KEY: str = "token-not-needed"
    LOCAL_QWEN_BASE_URL: str = "http://100.64.0.6:8100/v1"

    # JWT
    JWT_SECRET_KEY: str = "change-this"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    AUTH_REFRESH_COOKIE_NAME: str = "refresh_token"
    AUTH_REFRESH_COOKIE_SECURE: bool = False
    AUTH_REFRESH_COOKIE_SAMESITE: str = "lax"
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def CORS_ORIGIN_LIST(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)


settings = Settings()
