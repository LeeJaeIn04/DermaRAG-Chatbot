from collections.abc import Iterator
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import (
    Session,
    sessionmaker,
)
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.products.db_models import ProductRecord, utc_now
from app.products.models import (
    ProductCandidate,
    ProductIngredientResult,
)
from app.products.repositories.sqlite import (
    SQLiteProductIngredientRepository,
)
from app.products.repositories import ProductCollectionEntry
from app.products.related_service import RelatedProductService


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


def test_preparation_cache_requires_completion_marker(
    repository: SQLiteProductIngredientRepository,
) -> None:
    product = make_product()
    expires_at = utc_now() + timedelta(days=90)
    repository.save_ingredients(
        product=product,
        result=make_result(),
        expires_at=expires_at,
    )

    assert repository.get_cached_preparation(
        product.source, product.product_id, utc_now()
    ) is None

    repository.mark_collection_complete(
        product,
        status="not_applicable",
        option_ids=[""],
        options=[],
        expires_at=expires_at,
        parser_version="test-v1",
    )
    cached = repository.get_cached_preparation(
        product.source, product.product_id, utc_now()
    )
    assert cached is not None
    assert cached.status == "not_applicable"


def test_legacy_48_option_records_are_not_complete_without_state(
    repository: SQLiteProductIngredientRepository,
) -> None:
    product = make_product("A000000241210").model_copy(
        update={"category": "color_makeup"}
    )
    expires_at = utc_now() + timedelta(days=90)
    for index in range(48):
        repository.save_ingredients(
            product=product,
            result=make_result(product.product_id),
            expires_at=expires_at,
            option_id=f"legacy-option-{index:02d}",
            option_name=f"합성 옵션 {index:02d}",
        )

    assert repository.get_cached_preparation(
        product.source,
        product.product_id,
        utc_now(),
    ) is None


def test_preparation_cache_rejects_partial_option_records(
    repository: SQLiteProductIngredientRepository,
) -> None:
    product = make_product()
    expires_at = utc_now() + timedelta(days=90)
    repository.save_ingredients(
        product=product,
        result=make_result(),
        expires_at=expires_at,
        option_id="option-a",
        option_name="19호",
    )
    repository.mark_collection_complete(
        product,
        status="ready",
        option_ids=["option-a", "option-b"],
        options=[],
        expires_at=expires_at,
        parser_version="test-v1",
    )

    assert repository.get_cached_preparation(
        product.source, product.product_id, utc_now()
    ) is None


def test_canonical_option_source_metadata_round_trips_in_cache(
    repository: SQLiteProductIngredientRepository,
) -> None:
    product = make_product("CANONICAL-METADATA")
    expires_at = utc_now() + timedelta(days=30)
    option_id = "canonical-option-key"
    repository.save_collection(
        product,
        entries=[
            ProductCollectionEntry(
                result=make_result(product.product_id),
                option_id=option_id,
                option_name="23 누카다미아",
            )
        ],
        status="ready",
        options=[
            {
                "internal_option_key": option_id,
                "source_option_id": "plan",
                "option_name": "23 누카다미아",
                "raw_option_name": "[기획] 23호 누카다미아",
                "normalized_name": "23누카다미아",
                "source_option_names": [
                    "[기획] 23호 누카다미아",
                    "단품/23 누카다미아",
                ],
                "source_option_ids": ["plan", "single"],
            }
        ],
        expires_at=expires_at,
        parser_version="test-canonical",
    )

    cached = repository.get_cached_preparation(
        product.source, product.product_id, utc_now()
    )
    assert cached is not None
    assert len(cached.options) == 1
    assert cached.options[0].option_name == "23 누카다미아"
    assert cached.options[0].source_option_names == (
        "[기획] 23호 누카다미아",
        "단품/23 누카다미아",
    )
    assert cached.options[0].source_option_ids == ("plan", "single")


def _save_complete_product(
    repository: SQLiteProductIngredientRepository,
    product_id: str,
    *,
    category: str,
    category_path: str,
    option_ingredients: list[tuple[str, str | None, list[str]]],
) -> ProductCandidate:
    product = make_product(product_id).model_copy(
        update={
            "product_name": f"합성 상품 {product_id}",
            "category": category,
            "category_path": category_path,
        }
    )
    entries = [
        ProductCollectionEntry(
            result=ProductIngredientResult(
                product_id=product_id,
                product_url=product.product_url,
                raw_ingredients=", ".join(ingredients),
                ingredients=ingredients,
                extraction_method="test",
                extraction_success=True,
            ),
            option_id=option_id,
            option_name=option_name,
        )
        for option_id, option_name, ingredients in option_ingredients
    ]
    status = "ready" if entries[0].option_id else "not_applicable"
    repository.save_collection(
        product,
        entries=entries,
        status=status,
        options=[],
        expires_at=utc_now() + timedelta(days=30),
        parser_version="test-v1",
    )
    return product


def test_related_products_rank_category_and_keep_option_matches(
    repository: SQLiteProductIngredientRepository,
) -> None:
    current = _save_complete_product(
        repository,
        "CURRENT",
        category="skincare",
        category_path="뷰티 > 스킨케어 > 크림",
        option_ingredients=[("", None, ["리모넨"])],
    )
    _save_complete_product(
        repository,
        "SAME",
        category="skincare",
        category_path="뷰티 > 스킨케어 > 로션",
        option_ingredients=[
            ("01", "밝은색", ["리모넨", "리날룰"]),
            ("02", "어두운색", ["리모넨"]),
        ],
    )
    _save_complete_product(
        repository,
        "PARENT",
        category="other",
        category_path="뷰티 > 스킨케어 > 세럼",
        option_ingredients=[("", None, ["리모넨"])],
    )
    _save_complete_product(
        repository,
        "OTHER",
        category="other",
        category_path="뷰티 > 헤어 > 샴푸",
        option_ingredients=[("", None, ["리모넨"])],
    )

    results = RelatedProductService(repository).find_related_products(
        [" 리모넨 ", "리날룰", "리모넨"],
        exclude_source=current.source,
        exclude_external_product_id=current.product_id,
        category="skincare",
        category_path="뷰티 > 스킨케어 > 크림",
        limit=10,
    )

    assert [result.external_product_id for result in results] == [
        "SAME",
        "PARENT",
        "OTHER",
    ]
    assert results[0].category_match_level == "same_category"
    assert results[1].category_match_level == "same_parent_path"
    assert results[2].category_match_level == "other_category"
    assert results[0].matched_ingredients == ["리모넨", "리날룰"]
    assert len(results[0].matched_options) == 2
    assert results[0].matched_options[0].matched_ingredients == [
        "리모넨",
        "리날룰",
    ]
    without_same = RelatedProductService(repository).find_related_products(
        ["리모넨"], exclude_product_id=results[0].product_id, limit=10
    )
    assert "SAME" not in {
        result.external_product_id for result in without_same
    }


def test_related_products_use_exact_normalized_match_and_limit(
    repository: SQLiteProductIngredientRepository,
) -> None:
    _save_complete_product(
        repository,
        "EXACT",
        category="skincare",
        category_path="뷰티 > 스킨케어",
        option_ingredients=[("", None, ["프로판다이올"])],
    )
    _save_complete_product(
        repository,
        "PARTIAL",
        category="skincare",
        category_path="뷰티 > 스킨케어",
        option_ingredients=[("", None, ["프로판"])],
    )
    results = RelatedProductService(repository).find_related_products(
        ["프로판다이올"], limit=1
    )
    assert [result.external_product_id for result in results] == ["EXACT"]


def test_related_products_exclude_legacy_by_default(
    repository: SQLiteProductIngredientRepository,
) -> None:
    product = make_product("LEGACY")
    repository.save_ingredients(
        product,
        ProductIngredientResult(
            product_id="LEGACY",
            product_url=product.product_url,
            raw_ingredients="리모넨",
            ingredients=["리모넨"],
            extraction_method="legacy",
            extraction_success=True,
        ),
        expires_at=utc_now() + timedelta(days=30),
    )
    service = RelatedProductService(repository)
    assert service.find_related_products(["리모넨"]) == []
    assert len(
        service.find_related_products(["리모넨"], include_legacy=True)
    ) == 1


def test_related_products_empty_input_returns_empty(
    repository: SQLiteProductIngredientRepository,
) -> None:
    assert RelatedProductService(repository).find_related_products(
        ["", "  "]
    ) == []


def test_atomic_collection_failure_preserves_previous_complete_cache(
    repository: SQLiteProductIngredientRepository,
) -> None:
    product = _save_complete_product(
        repository,
        "ATOMIC",
        category="skincare",
        category_path="뷰티 > 스킨케어",
        option_ingredients=[("", None, ["정제수", "글리세린"])],
    )
    invalid = ProductCollectionEntry(
        result=ProductIngredientResult(
            product_id=product.product_id,
            product_url=product.product_url,
            raw_ingredients="",
            ingredients=[],
            extraction_method="test",
            extraction_success=False,
        )
    )
    with pytest.raises(ValueError):
        repository.save_collection(
            product,
            entries=[invalid],
            status="not_applicable",
            options=[],
            expires_at=utc_now() + timedelta(days=30),
            parser_version="test-v2",
        )
    cached = repository.get_cached_ingredients(
        product.source, product.product_id
    )
    assert cached is not None
    assert cached.ingredients == ("정제수", "글리세린")
    assert repository.get_cached_preparation(
        product.source, product.product_id, utc_now()
    ) is not None


def test_search_cache_saves_basic_products_and_expires(
    repository: SQLiteProductIngredientRepository,
) -> None:
    searched_at = utc_now()
    expires_at = searched_at + timedelta(hours=1)
    product = make_product("SEARCH-CACHE")
    repository.save_search_results(
        "라운드랩 선크림",
        [product],
        searched_at=searched_at,
        expires_at=expires_at,
    )

    cached = repository.get_cached_search(
        "라운드랩 선크림", now=searched_at
    )
    assert cached is not None
    assert [item.product_id for item in cached.products] == ["SEARCH-CACHE"]
    assert repository.get_product_candidate(
        product.source, product.product_id
    ) is not None
    assert repository.get_cached_preparation(
        product.source, product.product_id, searched_at
    ) is None
    assert repository.get_cached_search(
        "라운드랩 선크림", now=expires_at
    ) is None


def test_empty_search_result_is_cached_without_products(
    repository: SQLiteProductIngredientRepository,
) -> None:
    searched_at = utc_now()
    repository.save_search_results(
        "결과 없음",
        [],
        searched_at=searched_at,
        expires_at=searched_at + timedelta(minutes=10),
    )
    cached = repository.get_cached_search("결과 없음", now=searched_at)
    assert cached is not None
    assert cached.products == ()


def test_saved_product_basic_info_is_searchable_without_detail_cache(
    repository: SQLiteProductIngredientRepository,
) -> None:
    searched_at = utc_now()
    product = make_product("BASIC-SEARCH").model_copy(
        update={"product_name": "수요 기반 합성 선크림"}
    )
    repository.save_search_results(
        "첫 검색어",
        [product],
        searched_at=searched_at,
        expires_at=searched_at + timedelta(hours=1),
    )
    results = repository.search_products_by_text(
        "합성 선크림",
        now=searched_at,
        limit=5,
    )
    assert [result.product_id for result in results] == ["BASIC-SEARCH"]
    assert repository.search_products_by_text(
        "합성 선크림",
        now=searched_at + timedelta(hours=1),
        limit=5,
    ) == []
    assert repository.get_cached_preparation(
        product.source, product.product_id, searched_at
    ) is None


def test_product_name_search_uses_leading_bracket_normalization(
    repository: SQLiteProductIngredientRepository,
) -> None:
    searched_at = utc_now()
    original_name = "[NEW두유코어/1등틴트] 롬앤 더 쥬시 래스팅 틴트"
    product = make_product("NORMALIZED-SEARCH").model_copy(
        update={"product_name": original_name}
    )
    repository.save_search_results(
        "초기 검색",
        [product],
        searched_at=searched_at,
        expires_at=searched_at + timedelta(hours=1),
    )

    plain = repository.search_products_by_text(
        "롬앤 더 쥬시", now=searched_at, limit=5
    )
    promoted = repository.search_products_by_text(
        "[기획] 롬앤 더 쥬시", now=searched_at, limit=5
    )

    assert [item.product_id for item in plain] == ["NORMALIZED-SEARCH"]
    assert [item.product_id for item in promoted] == ["NORMALIZED-SEARCH"]
    assert plain[0].product_name == original_name

    with repository.session_factory() as session:
        stored = session.scalars(
            select(ProductRecord).where(
                ProductRecord.external_product_id == "NORMALIZED-SEARCH"
            )
        ).one()
        assert stored.product_name == original_name
        assert (
            stored.normalized_product_name
            == "롬앤 더 쥬시 래스팅 틴트"
        )

    updated_name = "[기획][단독] 롬앤 틴트"
    repository.save_search_results(
        "갱신 검색",
        [product.model_copy(update={"product_name": updated_name})],
        searched_at=searched_at,
        expires_at=searched_at + timedelta(hours=1),
    )
    with repository.session_factory() as session:
        updated = session.scalars(
            select(ProductRecord).where(
                ProductRecord.external_product_id == "NORMALIZED-SEARCH"
            )
        ).one()
        assert updated.product_name == updated_name
        assert updated.normalized_product_name == "롬앤 틴트"


def test_collection_queue_failure_uses_backoff_and_retry_count(
    repository: SQLiteProductIngredientRepository,
) -> None:
    product = make_product("QUEUE-FAIL")
    now = utc_now()
    first = repository.start_collection_attempt(product, now=now)
    assert first.status == "collecting"
    assert first.attempt_started is True
    assert first.attempt_count == 1

    failed = repository.finish_collection_attempt(
        product,
        success=False,
        now=now,
        retry_base_seconds=60,
        retry_max_seconds=600,
    )
    assert failed.status == "failed"
    assert failed.next_retry_at == now + timedelta(seconds=60)

    blocked = repository.start_collection_attempt(
        product, now=now + timedelta(seconds=59)
    )
    assert blocked.attempt_started is False
    assert blocked.attempt_count == 1

    second = repository.start_collection_attempt(
        product, now=now + timedelta(seconds=60)
    )
    assert second.attempt_started is True
    assert second.attempt_count == 2
    failed_again = repository.finish_collection_attempt(
        product,
        success=False,
        now=now + timedelta(seconds=60),
        retry_base_seconds=60,
        retry_max_seconds=600,
    )
    assert failed_again.next_retry_at == now + timedelta(seconds=180)


def test_collecting_lease_blocks_until_stale_then_claims_once(
    repository: SQLiteProductIngredientRepository,
    caplog,
) -> None:
    product = make_product("QUEUE-STALE")
    now = utc_now()
    first = repository.start_collection_attempt(
        product,
        now=now,
        collecting_lease_timeout_seconds=90,
    )
    assert first.attempt_started is True
    assert first.attempt_count == 1

    boundary = repository.start_collection_attempt(
        product,
        now=now + timedelta(seconds=90),
        collecting_lease_timeout_seconds=90,
    )
    assert boundary.attempt_started is False
    assert boundary.attempt_count == 1

    caplog.set_level("WARNING")
    recovered = repository.start_collection_attempt(
        product,
        now=now + timedelta(seconds=91),
        collecting_lease_timeout_seconds=90,
    )
    assert recovered.attempt_started is True
    assert recovered.status == "collecting"
    assert recovered.attempt_count == 2
    assert recovered.next_retry_at is None
    assert "Recovered stale product collection lease" in caplog.text


def test_new_repository_instance_recovers_persisted_stale_collecting(
    repository: SQLiteProductIngredientRepository,
) -> None:
    product = make_product("QUEUE-RESTART")
    now = utc_now()
    repository.start_collection_attempt(
        product,
        now=now,
        collecting_lease_timeout_seconds=60,
    )

    restarted = SQLiteProductIngredientRepository(
        repository.session_factory
    )
    recovered = restarted.start_collection_attempt(
        product,
        now=now + timedelta(seconds=61),
        collecting_lease_timeout_seconds=60,
    )
    assert recovered.attempt_started is True
    assert recovered.attempt_count == 2


def test_concurrent_stale_collecting_is_claimed_by_one_process(
    tmp_path,
) -> None:
    database_path = tmp_path / "stale-queue.db"
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False, "timeout": 5},
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
        class_=Session,
    )
    product = make_product("QUEUE-CONCURRENT-STALE")
    now = utc_now()
    SQLiteProductIngredientRepository(
        session_factory
    ).start_collection_attempt(
        product,
        now=now,
        collecting_lease_timeout_seconds=30,
    )
    barrier = Barrier(2)

    def claim():
        barrier.wait(timeout=2)
        return SQLiteProductIngredientRepository(
            session_factory
        ).start_collection_attempt(
            product,
            now=now + timedelta(seconds=31),
            collecting_lease_timeout_seconds=30,
        )

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: claim(), range(2)))
        assert sum(result.attempt_started for result in results) == 1
        assert {result.attempt_count for result in results} == {2}
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_stale_collecting_is_eligible_for_queue_worker(
    repository: SQLiteProductIngredientRepository,
) -> None:
    product = make_product("QUEUE-STALE-WORKER")
    now = utc_now()
    repository.start_collection_attempt(
        product,
        now=now,
        collecting_lease_timeout_seconds=90,
    )
    assert repository.list_collection_queue(
        now=now + timedelta(seconds=90),
        limit=10,
        collecting_lease_timeout_seconds=90,
    ) == []
    eligible = repository.list_collection_queue(
        now=now + timedelta(seconds=91),
        limit=10,
        collecting_lease_timeout_seconds=90,
    )
    assert [item.product.product_id for item in eligible] == [
        "QUEUE-STALE-WORKER"
    ]


def test_collection_queue_list_applies_execution_limit(
    repository: SQLiteProductIngredientRepository,
) -> None:
    now = utc_now()
    for index in range(3):
        product = make_product(f"QUEUE-{index}")
        repository.save_search_results(
            f"queue query {index}",
            [product],
            searched_at=now,
            expires_at=now + timedelta(hours=1),
        )
    queued = repository.list_collection_queue(now=now, limit=2)
    assert len(queued) == 2
    assert all(item.status == "pending" for item in queued)
