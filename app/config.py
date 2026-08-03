from typing import Annotated, Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PositiveInt = Annotated[int, Field(gt=0)]
NonNegativeInt = Annotated[int, Field(ge=0)]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", extra="ignore", env_ignore_empty=True
    )

    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_model: str = "qwen3:4b-instruct"
    ollama_timeout: PositiveInt = 120

    smtp_host: str = "localhost"
    smtp_port: PositiveInt = 1025
    smtp_timeout: PositiveInt = 10
    mail_from: str = "router@example.com"

    department_domain: str = "example.com"

    max_message_chars: PositiveInt = 4000
    max_body_bytes: PositiveInt = 65536
    max_concurrent_runs: PositiveInt = 2
    request_timeout: PositiveInt = 120
    retry_after_seconds: PositiveInt = 10

    agent_retries: NonNegativeInt = 1
    warmup_on_startup: bool = True
    ready_timeout: PositiveInt = 5

    log_level: LogLevel = "INFO"


settings = Settings()
