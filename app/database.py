import os
from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import (
    DeclarativeBase,
    Session,
    sessionmaker,
)


# 로컬 SQLite 파일을 저장할 폴더다.
# 폴더가 없으면 애플리케이션 실행 시 생성한다.
DATA_DIRECTORY = Path("data")
DATA_DIRECTORY.mkdir(
    parents=True,
    exist_ok=True,
)


# 운영 환경에서는 DATABASE_URL 환경변수를 사용할 수 있고,
# 설정하지 않으면 로컬 SQLite DB를 사용한다.
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///./data/derma_rag.db",
)


# SQLite는 기본적으로 하나의 thread에서 생성한 연결을
# 다른 thread에서 사용하지 못하게 한다.
#
# FastAPI는 요청을 다른 thread에서 처리할 수 있으므로
# SQLite를 사용할 때 check_same_thread=False가 필요하다.
connect_args: dict[str, bool] = {}

if DATABASE_URL.startswith("sqlite"):
    connect_args = {
        "check_same_thread": False,
    }


# 애플리케이션에서 공유할 DB engine이다.
engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
)


# DB 작업마다 SessionLocal()로 독립적인 session을 만든다.
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """
    SQLAlchemy DB 모델이 상속할 공통 Base 클래스.
    """

    pass


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI endpoint에서 사용할 DB session을 제공한다.

    요청 처리가 끝나면 성공·실패 여부와 관계없이
    session을 닫는다.
    """

    database = SessionLocal()

    try:
        yield database
    finally:
        database.close()

def create_database_tables() -> None:
    """
    SQLAlchemy에 등록된 모든 테이블을 생성한다.

    반드시 DB 모델을 import한 뒤 실행해야
    Base.metadata가 해당 테이블을 인식할 수 있다.
    """

    # import가 실행되면 ProductRecord 등의 모델이
    # Base.metadata에 등록된다.
    from app.products import db_models  # noqa: F401

    Base.metadata.create_all(
        bind=engine
    )