from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # 애플리케이션 환경
    APP_ENV: str

    # RabbitMQ
    RABBITMQ_URL: str

    # Meilisearch
    MEILI_URL: str
    MEILI_MASTER_KEY: str

    # OpenAI
    OPENAI_API_KEY: str

    # GitHub Token (선택 사항)
    # Public Repository는 Token 없이도 접근 가능 (Rate Limit: 60 req/hour)
    # Token이 있으면 Rate Limit: 5000 req/hour
    GITHUB_TOKEN: str = ""

    # GitHub Client 설정
    MAX_ZIP_SIZE_MB: int = 50

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


def get_settings() -> Settings:
    return Settings()