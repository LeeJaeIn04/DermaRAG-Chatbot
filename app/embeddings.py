from langchain_core.embeddings import Embeddings
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_huggingface import HuggingFaceEmbeddings
from app.config import settings

def get_embedding_model_name() -> str:
    if settings.embedding_provider == "gemini":
        return settings.gemini_embedding_model

    return settings.local_embedding_model


def get_embeddings() -> Embeddings:
    if settings.embedding_provider == "gemini":
        if not settings.google_api_key:
            raise RuntimeError(
                "GOOGLE_API_KEY가 설정되어 있지 않습니다. "
                ".env 파일에 Gemini API Key를 추가해 주세요."
            )

        return GoogleGenerativeAIEmbeddings(
            model=settings.gemini_embedding_model,
            google_api_key=settings.google_api_key,
        )

    if settings.embedding_provider == "local":
        return HuggingFaceEmbeddings(
            model_name=settings.local_embedding_model,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )

    raise ValueError(
        f"지원하지 않는 embedding_provider입니다: {settings.embedding_provider}"
    )