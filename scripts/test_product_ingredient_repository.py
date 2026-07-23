from collections.abc import Iterator
from datetime import timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import (
    Session,
    sessionmaker,
)
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.products.db_models import utc_now
from app.products.models import (
    ProductCandidate,
    ProductIngredientResult,
)
from app.products.repositories.sqlite import (
    SQLiteProductIngredientRepository,
)


@pytest.fixture
def repository(
) -> Iterator[
    SQLiteProductIngredientRepository
]:
    """
    각 테스트에서 사용할 임시 메모리 SQLite DB를 만든다.

    실제 data/derma_rag.db를 사용하지 않으므로
    개발 DB를 오염시키지 않는다.
    """

    engine = create_engine(
        "sqlite://",
        connect_args={
            "check_same_thread": False,
        },
        poolclass=StaticPool,
    )

    # db_models가 import된 상태이므로
    # Base.metadata에 세 테이블이 등록돼 있다.
    Base.metadata.create_all(bind=engine)

    test_session_factory = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
        class_=Session,
    )

    yield SQLiteProductIngredientRepository(
        session_factory=test_session_factory,
    )

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def make_product(
    product_id: str = "A000000149135",
) -> ProductCandidate:
    """
    테스트에서 반복 사용할 상품 후보를 생성한다.
    """

    return ProductCandidate(
        product_id=product_id,
        source="oliveyoung",
        brand_name="라운드랩",
        product_name="자작나무 수분 선크림",
        category="skincare",
        category_path="스킨케어 > 선케어",
        product_url=(
            "https://www.oliveyoung.co.kr/store/goods/"
            f"getGoodsDetail.do?goodsNo={product_id}"
        ),
        image_url=None,
    )


def make_result(
    product_id: str = "A000000149135",
) -> ProductIngredientResult:
    """
    테스트용 전성분 추출 성공 결과를 생성한다.
    """

    ingredients = [
        "정제수",
        "글리세린",
        "나이아신아마이드",
    ]

    return ProductIngredientResult(
        product_id=product_id,
        product_url=(
            "https://www.oliveyoung.co.kr/store/goods/"
            f"getGoodsDetail.do?goodsNo={product_id}"
        ),
        raw_ingredients=", ".join(ingredients),
        ingredients=ingredients,
        extraction_method="browser_dom",
        extraction_success=True,
        error_message=None,
    )


def test_returns_none_when_cache_is_missing(
    repository: SQLiteProductIngredientRepository,
) -> None:
    """
    저장되지 않은 상품은 None을 반환해야 한다.
    """

    cached = repository.get_cached_ingredients(
        source="oliveyoung",
        external_product_id="UNKNOWN",
    )

    assert cached is None


def test_saves_and_loads_ingredients(
    repository: SQLiteProductIngredientRepository,
) -> None:
    """
    상품과 전성분을 저장한 뒤 동일한 순서로 조회한다.
    """

    product = make_product()
    result = make_result()
    expires_at = utc_now() + timedelta(days=90)

    saved = repository.save_ingredients(
        product=product,
        result=result,
        expires_at=expires_at,
    )

    loaded = repository.get_cached_ingredients(
        source=product.source,
        external_product_id=product.product_id,
    )

    assert loaded is not None
    assert saved.product_id == product.product_id
    assert loaded.product_id == product.product_id
    assert loaded.source == "oliveyoung"
    assert loaded.raw_ingredients == (
        result.raw_ingredients
    )
    assert list(loaded.ingredients) == (
        result.ingredients
    )
    assert loaded.expires_at == expires_at
    assert loaded.ingredient_hash


def test_updates_existing_ingredients(
    repository: SQLiteProductIngredientRepository,
) -> None:
    """
    같은 상품을 다시 저장하면 중복 레코드 대신
    기존 전성분과 개별 성분 목록을 갱신해야 한다.
    """

    product = make_product()

    first_result = make_result()

    repository.save_ingredients(
        product=product,
        result=first_result,
        expires_at=(
            utc_now() + timedelta(days=30)
        ),
    )

    updated_ingredients = [
        "정제수",
        "판테놀",
    ]

    updated_result = ProductIngredientResult(
        product_id=product.product_id,
        product_url=product.product_url,
        raw_ingredients=", ".join(
            updated_ingredients
        ),
        ingredients=updated_ingredients,
        extraction_method="browser_dom",
        extraction_success=True,
        error_message=None,
    )

    new_expires_at = (
        utc_now() + timedelta(days=90)
    )

    repository.save_ingredients(
        product=product,
        result=updated_result,
        expires_at=new_expires_at,
    )

    loaded = repository.get_cached_ingredients(
        source=product.source,
        external_product_id=product.product_id,
    )

    assert loaded is not None
    assert list(loaded.ingredients) == (
        updated_ingredients
    )
    assert "나이아신아마이드" not in (
        loaded.ingredients
    )
    assert loaded.expires_at == new_expires_at


def test_rejects_failed_extraction(
    repository: SQLiteProductIngredientRepository,
) -> None:
    """
    추출 실패 결과는 정상 캐시로 저장하면 안 된다.
    """

    product = make_product()

    failed_result = ProductIngredientResult(
        product_id=product.product_id,
        product_url=product.product_url,
        raw_ingredients="",
        ingredients=[],
        extraction_method="browser_dom",
        extraction_success=False,
        error_message="추출 실패",
    )

    with pytest.raises(
        ValueError,
        match="추출에 실패한",
    ):
        repository.save_ingredients(
            product=product,
            result=failed_result,
            expires_at=(
                utc_now() + timedelta(days=90)
            ),
        )


def test_finds_products_by_ingredient(
    repository: SQLiteProductIngredientRepository,
) -> None:
    """
    정규화된 성분명으로 해당 성분을 포함한 상품을 찾는다.
    """

    product_a = make_product(
        "PRODUCT-A"
    )
    result_a = ProductIngredientResult(
        product_id="PRODUCT-A",
        product_url=product_a.product_url,
        raw_ingredients=(
            "정제수, 나이아신아마이드"
        ),
        ingredients=[
            "정제수",
            "나이아신아마이드",
        ],
        extraction_method="test",
        extraction_success=True,
        error_message=None,
    )

    product_b = make_product(
        "PRODUCT-B"
    )
    result_b = ProductIngredientResult(
        product_id="PRODUCT-B",
        product_url=product_b.product_url,
        raw_ingredients="정제수, 판테놀",
        ingredients=[
            "정제수",
            "판테놀",
        ],
        extraction_method="test",
        extraction_success=True,
        error_message=None,
    )

    expires_at = (
        utc_now() + timedelta(days=90)
    )

    repository.save_ingredients(
        product=product_a,
        result=result_a,
        expires_at=expires_at,
    )
    repository.save_ingredients(
        product=product_b,
        result=result_b,
        expires_at=expires_at,
    )

    products = (
        repository.find_products_by_ingredient(
            " 나이아신아마이드 ",
        )
    )

    assert len(products) == 1
    assert products[0].product_id == "PRODUCT-A"