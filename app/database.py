from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import (
    DeclarativeBase,
    Session,
    sessionmaker,
)

from app.config import settings


# 로컬 SQLite 파일을 저장할 폴더다.
# 폴더가 없으면 애플리케이션 실행 시 생성한다.
DATA_DIRECTORY = Path("data")
DATA_DIRECTORY.mkdir(
    parents=True,
    exist_ok=True,
)


# 운영 환경에서는 DATABASE_URL 환경변수를 사용할 수 있고,
# 설정하지 않으면 로컬 SQLite DB를 사용한다.
DATABASE_URL = settings.database_url


# SQLite는 기본적으로 하나의 thread에서 생성한 연결을
# 다른 thread에서 사용하지 못하게 한다.
#
# FastAPI는 요청을 다른 thread에서 처리할 수 있으므로
# SQLite를 사용할 때 check_same_thread=False가 필요하다.
connect_args: dict[str, bool | float] = {}

if DATABASE_URL.startswith("sqlite"):
    connect_args = {
        "check_same_thread": False,
        "timeout": settings.sqlite_busy_timeout_ms / 1_000,
    }


# 애플리케이션에서 공유할 DB engine이다.
engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
)


if DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _configure_sqlite_connection(
        dbapi_connection,
        _connection_record,
    ) -> None:
        """각 SQLite 연결에 무결성과 동시성 관련 PRAGMA를 적용한다."""

        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute(
                "PRAGMA busy_timeout="
                f"{settings.sqlite_busy_timeout_ms}"
            )
            cursor.execute("PRAGMA journal_mode=WAL")
        finally:
            cursor.close()


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

_OPTION_CACHE_COLUMNS_BY_TABLE: dict[str, tuple[tuple[str, str], ...]] = {
    "product_collection_states": (
        ("option_cache_collection_status", "VARCHAR(20)"),
        ("option_cache_parser_version", "VARCHAR(50)"),
        ("option_cache_diagnostics_json", "TEXT"),
        ("option_cache_option_count", "INTEGER"),
    ),
    "product_ingredient_records": (
        ("option_cache_status", "VARCHAR(20)"),
        ("option_cache_mapped_section_id", "VARCHAR(100)"),
        ("option_cache_parser_version", "VARCHAR(50)"),
        ("option_cache_diagnostics_json", "TEXT"),
    ),
}


def migrate_option_cache_columns(target_engine=None) -> None:
    """Step 3 option-level cache용 nullable 컬럼을 additive하게 추가한다.

    `PRAGMA table_info`로 이미 있는 컬럼은 건너뛰므로 몇 번을
    다시 실행해도 안전하다(idempotent). 테이블이 아직 없으면
    아무것도 하지 않는다 - `Base.metadata.create_all()`이 새
    컬럼까지 포함해 테이블을 만들어 준다. 기존 컬럼/테이블은 절대
    변경하거나 지우지 않는다.
    """

    active_engine = target_engine if target_engine is not None else engine
    if active_engine.dialect.name != "sqlite":
        return

    with active_engine.begin() as connection:
        for table_name, columns in _OPTION_CACHE_COLUMNS_BY_TABLE.items():
            table_exists = connection.execute(
                text(
                    "SELECT 1 FROM sqlite_master "
                    "WHERE type = 'table' AND name = :table_name"
                ),
                {"table_name": table_name},
            ).first()
            if table_exists is None:
                continue

            existing_columns = {
                row[1]
                for row in connection.execute(
                    text(f"PRAGMA table_info({table_name})")
                )
            }
            for column_name, ddl_type in columns:
                if column_name in existing_columns:
                    continue
                connection.execute(
                    text(
                        f"ALTER TABLE {table_name} "
                        f"ADD COLUMN {column_name} {ddl_type}"
                    )
                )


def create_database_tables() -> None:
    """
    SQLAlchemy에 등록된 모든 테이블을 생성한다.

    반드시 DB 모델을 import한 뒤 실행해야
    Base.metadata가 해당 테이블을 인식할 수 있다.
    """

    # import가 실행되면 ProductRecord 등의 모델이
    # Base.metadata에 등록된다.
    from app.products import db_models  # noqa: F401
    from app.products.product_name_normalization import normalize_product_name

    # 기존 SQLite의 products 테이블에는 create_all()만으로 새 컬럼이
    # 추가되지 않는다. 새 index 생성보다 먼저 컬럼을 보강한다.
    if engine.dialect.name == "sqlite":
        with engine.begin() as connection:
            products_exists = connection.execute(
                text(
                    "SELECT 1 FROM sqlite_master "
                    "WHERE type = 'table' AND name = 'products'"
                )
            ).first()
            if products_exists is not None:
                product_columns = {
                    row[1]
                    for row in connection.execute(
                        text("PRAGMA table_info(products)")
                    )
                }
                if "normalized_product_name" not in product_columns:
                    connection.execute(
                        text(
                            "ALTER TABLE products ADD COLUMN "
                            "normalized_product_name VARCHAR(500) "
                            "NOT NULL DEFAULT ''"
                        )
                    )

    migrate_option_cache_columns(engine)

    Base.metadata.create_all(bind=engine)

    # create_all()은 기존 테이블에 새 index를 추가하지 않으므로
    # idempotent schema upgrade로 기존 SQLite DB도 보강한다.
    if engine.dialect.name == "sqlite":
        with engine.begin() as connection:
            # 기존 표시용 product_name은 변경하지 않고 검색용 컬럼만
            # 현재 정규화 규칙으로 안전하게 backfill한다.
            products = connection.execute(
                text(
                    "SELECT id, product_name, normalized_product_name "
                    "FROM products"
                )
            ).mappings()
            for product in products:
                normalized_name = normalize_product_name(
                    product["product_name"]
                )
                if product["normalized_product_name"] == normalized_name:
                    continue
                connection.execute(
                    text(
                        "UPDATE products SET normalized_product_name = "
                        ":normalized_name WHERE id = :product_id"
                    ),
                    {
                        "normalized_name": normalized_name,
                        "product_id": product["id"],
                    },
                )

            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS "
                    "ix_products_normalized_product_name "
                    "ON products (normalized_product_name)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_products_category "
                    "ON products (category)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_products_category_path "
                    "ON products (category_path)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS "
                    "ix_product_ingredient_records_product_id "
                    "ON product_ingredient_records (product_id)"
                )
            )
