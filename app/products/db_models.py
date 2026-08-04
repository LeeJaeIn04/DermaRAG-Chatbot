from __future__ import annotations

from datetime import datetime, UTC
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship,
)

from app.database import Base


if TYPE_CHECKING:
    # 타입 검사 도구가 관계 필드의 타입을 이해하도록 돕는다.
    # 실제 실행 시에는 아래 클래스들이 같은 파일에 있으므로
    # 별도의 runtime import는 필요하지 않다.
    pass


def utc_now() -> datetime:
    """
    현재 UTC 시각을 SQLite 저장용 naive datetime으로 반환한다.
    """

    return datetime.now(UTC).replace(
        tzinfo=None
    )


class ProductRecord(Base):
    """
    쇼핑몰에서 검색한 상품의 기본 정보를 저장한다.

    같은 상품이 여러 번 검색되더라도
    source와 external_product_id가 같으면
    하나의 상품으로 관리한다.
    """

    __tablename__ = "products"

    __table_args__ = (
        # 쇼핑몰과 외부 상품 ID의 조합은 유일해야 한다.
        UniqueConstraint(
            "source",
            "external_product_id",
            name="uq_products_source_external_id",
        ),
        Index("ix_products_category", "category"),
        Index("ix_products_category_path", "category_path"),
    )

    # DB 내부에서 사용하는 숫자 ID
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    # 상품 데이터 출처
    # 예: oliveyoung, naver, mock_oliveyoung
    source: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    # 외부 서비스의 상품 ID
    # 올리브영에서는 goodsNo에 해당한다.
    external_product_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    brand_name: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    product_name: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    # 검색·비교 전용 값이다. 사용자에게 표시하는 product_name은
    # provider에서 받은 원문을 그대로 보존한다.
    normalized_product_name: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        default="",
        index=True,
    )

    # skincare, color_makeup, other, unknown
    category: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="unknown",
    )

    category_path: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    product_url: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    image_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        default=utc_now,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    # 한 상품은 스킨케어 전성분 하나 또는
    # 여러 색조 옵션의 전성분을 가질 수 있다.
    ingredient_records: Mapped[
        list[ProductIngredientRecord]
    ] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
    )

    collection_state: Mapped[ProductCollectionState | None] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
        uselist=False,
    )

    search_results: Mapped[list[ProductSearchResultRecord]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
    )

    collection_queue: Mapped[ProductCollectionQueueRecord | None] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
        uselist=False,
    )


class ProductSearchQueryRecord(Base):
    __tablename__ = "product_search_queries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    normalized_query: Mapped[str] = mapped_column(
        String(500), nullable=False, unique=True
    )
    searched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, index=True
    )
    results: Mapped[list[ProductSearchResultRecord]] = relationship(
        back_populates="query",
        cascade="all, delete-orphan",
        order_by="ProductSearchResultRecord.rank",
    )


class ProductSearchResultRecord(Base):
    __tablename__ = "product_search_results"
    __table_args__ = (
        UniqueConstraint(
            "query_id", "product_id", name="uq_search_results_query_product"
        ),
        UniqueConstraint(
            "query_id", "rank", name="uq_search_results_query_rank"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    query_id: Mapped[int] = mapped_column(
        ForeignKey("product_search_queries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    query: Mapped[ProductSearchQueryRecord] = relationship(
        back_populates="results"
    )
    product: Mapped[ProductRecord] = relationship(
        back_populates="search_results"
    )


class ProductCollectionQueueRecord(Base):
    __tablename__ = "product_collection_queue"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="pending", index=True
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False), nullable=True
    )
    next_retry_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False), nullable=True, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, default=utc_now, onupdate=utc_now
    )
    product: Mapped[ProductRecord] = relationship(
        back_populates="collection_queue"
    )


class ProductCollectionState(Base):
    """상품 선택 단계에서 옵션/전성분 수집 완료 여부를 기록한다."""

    __tablename__ = "product_collection_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    option_count: Mapped[int] = mapped_column(Integer, nullable=False)
    parser_version: Mapped[str] = mapped_column(String(50), nullable=False)
    options_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, default=utc_now
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False
    )

    product: Mapped[ProductRecord] = relationship(
        back_populates="collection_state"
    )


class ProductIngredientRecord(Base):
    """
    한 상품 또는 한 상품 옵션의 전성분 추출 결과.

    스킨케어처럼 옵션이 없는 경우 option_id는 빈 문자열이다.

    색조 상품은 option_id를 사용해 호수별 전성분을 구분한다.
    """

    __tablename__ = "product_ingredient_records"

    __table_args__ = (
        # 같은 상품과 옵션에는 현재 캐시 레코드가
        # 하나만 존재하도록 제한한다.
        UniqueConstraint(
            "product_id",
            "option_id",
            name=(
                "uq_product_ingredient_records_"
                "product_option"
            ),
        ),
        Index(
            "ix_product_ingredient_records_product_id",
            "product_id",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    # products.id를 참조한다.
    product_id: Mapped[int] = mapped_column(
        ForeignKey(
            "products.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    # 스킨케어 등 옵션이 없는 상품은 ""를 사용한다.
    #
    # SQLite에서는 NULL이 들어간 unique column이
    # 여러 번 허용될 수 있으므로 None 대신 빈 문자열로
    # 옵션 없음 상태를 통일한다.
    option_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="",
    )

    option_name: Mapped[str | None] = mapped_column(
        String(300),
        nullable=True,
    )

    # 상품 페이지에서 가져온 전성분 원문
    raw_ingredients: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    # 전성분 원문을 정규화해서 만든 hash
    # 전성분 변경 여부를 확인하는 데 사용한다.
    ingredient_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    # browser_dom, manual, api 등의 추출 방법
    extraction_method: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    # 전성분을 실제로 추출한 시각
    extracted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        default=utc_now,
    )

    # 상품 페이지를 마지막으로 확인한 시각
    last_checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        default=utc_now,
    )

    # 이 시각 이후에는 캐시가 만료된 것으로 판단한다.
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
    )

    product: Mapped[ProductRecord] = relationship(
        back_populates="ingredient_records",
    )

    # 원문에서 분리한 개별 성분 목록
    ingredient_items: Mapped[
        list[ProductIngredientItem]
    ] = relationship(
        back_populates="ingredient_record",
        cascade="all, delete-orphan",
        order_by="ProductIngredientItem.position",
    )


class ProductIngredientItem(Base):
    """
    상품 전성분에서 분리한 개별 성분 하나.

    특정 성분을 포함한 상품을 역검색할 때
    normalized_name을 사용한다.
    """

    __tablename__ = "product_ingredient_items"

    __table_args__ = (
        # 한 전성분 목록 안에서 각 순서는 하나만 존재한다.
        UniqueConstraint(
            "ingredient_record_id",
            "position",
            name=(
                "uq_product_ingredient_items_"
                "record_position"
            ),
        ),

        # 성분명으로 상품을 검색할 때 사용할 index
        Index(
            "ix_product_ingredient_items_normalized_name",
            "normalized_name",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    ingredient_record_id: Mapped[int] = mapped_column(
        ForeignKey(
            "product_ingredient_records.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    # 상품 페이지에 표시된 개별 성분명
    ingredient_name: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    # 공백·대소문자 등의 검색 차이를 줄이기 위해
    # 정규화한 성분명
    normalized_name: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    # 상품 전성분 목록에서의 순서
    position: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    ingredient_record: Mapped[
        ProductIngredientRecord
    ] = relationship(
        back_populates="ingredient_items",
    )
