from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[1]
ENV_FILE = BASE_DIR / ".env"

# pydantic-settings reads .env into Settings, but that alone does not expose
# the values to libraries (such as LangSmith) that read os.environ directly.
# Preserve explicitly exported shell values by keeping override disabled.
def load_project_environment() -> None:
    load_dotenv(ENV_FILE, override=False)


load_project_environment()


class Settings(BaseSettings):
    google_api_key: str | None = None
    data_go_kr_service_key: str | None = None

    gemini_chat_model: str = "gemini-2.5-flash-lite"

    embedding_provider: str = "local"
    local_embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    gemini_embedding_model: str = "gemini-embedding-001"

    langsmith_tracing: bool = False
    langsmith_api_key: str | None = None
    langsmith_endpoint: str = "https://api.smith.langchain.com"
    langsmith_workspace_id: str | None = None
    langsmith_project: str = "derma-rag"

    database_url: str = "sqlite:///./data/derma_rag.db"
    sqlite_busy_timeout_ms: int = 5_000

    product_ingredient_ttl_days: int = 90
    product_search_cache_ttl_minutes: int = 1_440
    product_cache_only_mode: bool = False
    product_live_collection_enabled: bool = True
    product_collection_retry_base_seconds: int = 300
    product_collection_retry_max_seconds: int = 21_600
    product_collection_max_per_run: int = 10
    product_playwright_headless: bool = False
    product_playwright_timeout_ms: int = 60_000
    product_playwright_deadline_ms: int = 90_000
    product_playwright_max_attempts: int = 2

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
