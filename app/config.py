from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[1]
ENV_FILE = BASE_DIR / ".env"

class Settings(BaseSettings):
    google_api_key: str | None = None
    data_go_kr_service_key: str | None = None

    gemini_chat_model: str = "gemini-2.5-flash-lite"

    embedding_provider: str = "local"
    local_embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    gemini_embedding_model: str = "gemini-embedding-001"

    langsmith_tracing: bool = False
    langsmith_api_key: str | None = None
    langsmith_project: str = "derma-rag"

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

settings = Settings()