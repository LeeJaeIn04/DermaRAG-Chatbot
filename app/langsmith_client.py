import os
from collections.abc import Callable
from typing import TypeVar

from app.config import load_project_environment
from langsmith import Client
from langsmith.utils import LangSmithAuthError


ResultT = TypeVar("ResultT")


def create_langsmith_client() -> Client:
    """Create a Client after the project .env has been loaded."""

    load_project_environment()
    return Client()


def _auth_error_status(error: Exception) -> int | None:
    response = getattr(error, "response", None)
    status = getattr(response, "status_code", None)
    if isinstance(status, int):
        return status

    message = str(error)
    if isinstance(error, LangSmithAuthError) or "401 Client Error" in message:
        return 401
    if "403 Client Error" in message or "403 Forbidden" in message:
        return 403
    return None


def run_with_langsmith_auth_help(
    callback: Callable[[], ResultT],
) -> ResultT:
    """Add actionable 401/403 guidance without hiding other failures."""

    try:
        return callback()
    except Exception as error:
        status = _auth_error_status(error)
        if status == 401:
            raise SystemExit(
                "LangSmith 인증 실패(401): API 키가 유효한지, 만료되거나 "
                "폐기된 키가 셸에서 우선 적용되고 있지 않은지 확인하세요."
            ) from None
        if status == 403:
            workspace_is_set = bool(
                os.getenv("LANGSMITH_WORKSPACE_ID")
                or os.getenv("LANGCHAIN_WORKSPACE_ID")
            )
            workspace_help = (
                " 설정된 workspace ID가 PAT으로 접근 가능한 workspace와 "
                "일치하는지 확인하세요."
                if workspace_is_set
                else " PAT 사용자의 workspace 권한을 확인하세요."
            )
            raise SystemExit(
                "LangSmith 권한 거부(403): 인증은 처리됐지만 요청 대상에 "
                f"접근할 수 없습니다.{workspace_help}"
            ) from None
        raise
