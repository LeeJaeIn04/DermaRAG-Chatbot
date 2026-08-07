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
    # "development"일 때만 개발 전용 진단 endpoint(예: parser-debug)가
    # 활성화된다. 운영 배포는 이 값을 설정하지 않으면 안전하게
    # "production"으로 남는다.
    environment: str = "production"

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
    playwright_headless: bool = False
    product_playwright_timeout_ms: int = 60_000
    product_playwright_deadline_ms: int = 90_000
    product_playwright_max_attempts: int = 2

    # Step 2 selector 관찰 모드. true여도 cache 저장/API 응답은 항상
    # production 결과를 그대로 쓴다 - shadow/selector 판단은 로그에만
    # 남긴다. 기본값은 false로, 설정하지 않으면 관찰 모드는 꺼져 있다.
    product_shadow_observation_enabled: bool = False

    # Step 3 SQLite option-level cache. true여도 저장되는 값은 항상
    # production ParserResult뿐이다(shadow selected_result는 절대
    # 저장하지 않는다). 기본값은 false로, 꺼져 있으면 기존
    # legacy cache read/write만 그대로 동작한다.
    product_option_level_cache_enabled: bool = False

    # Step 6: production 전환. true면 Step 1 selector가 고른 결과
    # (production 또는 shadow)를 effective result로 써서 API 응답과
    # cache 저장에 그대로 반영한다. false면 지금까지처럼 production
    # 결과만 쓴다(완전 회귀 안전). 기본값 false.
    product_selected_parser_result_enabled: bool = False

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
