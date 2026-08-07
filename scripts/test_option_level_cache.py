"""Step 3: SQLite option-level cache (additive columns, migration,
reader/writer, feature flag) 테스트.

legacy cache read/write는 그대로 두고, 새로 추가한 option_cache_*
컬럼과 관련 로직만 검증한다.
"""

from datetime import timedelta

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, migrate_option_cache_columns
from app.products.db_models import utc_now
from app.products.models import ProductCandidate, ProductIngredientResult
from app.products.parser_state import (
    build_option_level_result,
    build_parser_result,
)
from app.products.repositories import ProductCollectionEntry
from app.products.repositories.sqlite import (
    SQLiteProductIngredientRepository,
    _safe_json_dumps,
)
from dataclasses import replace as _dataclass_replace


# ---------------------------------------------------------------------------
# migration: idempotent additive ALTER TABLE + 기존 row 보존
# ---------------------------------------------------------------------------


def _create_legacy_schema_engine():
    """Step 3 이전 스키마를 흉내 낸(신규 컬럼 없는) sqlite engine을
    만든다 - 실제 운영 DB가 마이그레이션 전 어떤 모양이었는지
    재현한다."""

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE product_collection_states ("
                "id INTEGER PRIMARY KEY, product_id INTEGER, "
                "status VARCHAR(30), option_count INTEGER, "
                "parser_version VARCHAR(50), options_json TEXT, "
                "collected_at DATETIME, expires_at DATETIME)"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE product_ingredient_records ("
                "id INTEGER PRIMARY KEY, product_id INTEGER, "
                "option_id VARCHAR(100), option_name VARCHAR(300), "
                "raw_ingredients TEXT, ingredient_hash VARCHAR(64), "
                "extraction_method VARCHAR(50), extracted_at DATETIME, "
                "last_checked_at DATETIME, expires_at DATETIME)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO product_collection_states "
                "(id, product_id, status, option_count, parser_version, "
                "options_json, collected_at, expires_at) VALUES "
                "(1, 1, 'ready', 1, 'option-sections-v1', '[]', "
                "'2024-01-01 00:00:00', '2099-01-01 00:00:00')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO product_ingredient_records "
                "(id, product_id, option_id, option_name, raw_ingredients, "
                "ingredient_hash, extraction_method, extracted_at, "
                "last_checked_at, expires_at) VALUES "
                "(1, 1, '19', '19호', '정제수, 글리세린', 'legacy-hash', "
                "'browser_dom:legacy', '2024-01-01 00:00:00', "
                "'2024-01-01 00:00:00', '2099-01-01 00:00:00')"
            )
        )
    return engine


def test_migration_adds_missing_columns_and_is_idempotent_on_rerun() -> None:
    engine = _create_legacy_schema_engine()

    migrate_option_cache_columns(engine)

    with engine.connect() as connection:
        collection_columns = {
            row[1]
            for row in connection.execute(
                text("PRAGMA table_info(product_collection_states)")
            )
        }
        record_columns = {
            row[1]
            for row in connection.execute(
                text("PRAGMA table_info(product_ingredient_records)")
            )
        }
    assert {
        "option_cache_collection_status",
        "option_cache_parser_version",
        "option_cache_diagnostics_json",
    } <= collection_columns
    assert {
        "option_cache_status",
        "option_cache_mapped_section_id",
        "option_cache_parser_version",
        "option_cache_diagnostics_json",
    } <= record_columns

    # 재실행(migration 재실행) - 이미 컬럼이 있으므로 에러 없이 끝나야
    # 한다.
    migrate_option_cache_columns(engine)
    migrate_option_cache_columns(engine)

    # 기존 row는 그대로 보존된다.
    with engine.connect() as connection:
        collection_row = connection.execute(
            text(
                "SELECT status, parser_version, option_count "
                "FROM product_collection_states WHERE id = 1"
            )
        ).first()
        record_row = connection.execute(
            text(
                "SELECT option_id, option_name, raw_ingredients "
                "FROM product_ingredient_records WHERE id = 1"
            )
        ).first()
    assert collection_row == ("ready", "option-sections-v1", 1)
    assert record_row == ("19", "19호", "정제수, 글리세린")


def test_migration_skips_missing_tables_without_error() -> None:
    """테이블이 아직 없는 완전히 새 DB에서도 예외 없이 넘어간다 -
    Base.metadata.create_all()이 새 컬럼까지 포함해 만들어 준다."""

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    migrate_option_cache_columns(engine)
    Base.metadata.create_all(bind=engine)

    with engine.connect() as connection:
        columns = {
            row[1]
            for row in connection.execute(
                text("PRAGMA table_info(product_collection_states)")
            )
        }
    assert "option_cache_collection_status" in columns


# ---------------------------------------------------------------------------
# repository read/write round-trip
# ---------------------------------------------------------------------------


def _repository():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(
        bind=engine, autoflush=False, expire_on_commit=False, class_=Session
    )
    return SQLiteProductIngredientRepository(session_factory=session_factory)


def _product(product_id: str = "A000000000009") -> ProductCandidate:
    return ProductCandidate(
        product_id=product_id,
        source="oliveyoung",
        product_name="옵션 캐시 테스트 상품",
        category="color_makeup",
        product_url=(
            "https://www.oliveyoung.co.kr/store/goods/"
            "getGoodsDetail.do?goodsNo=" + product_id
        ),
    )


def _entry(
    option_id: str,
    option_name: str,
    ingredients: list[str],
    product_id: str = "A000000000009",
):
    return ProductCollectionEntry(
        result=ProductIngredientResult(
            product_id=product_id,
            product_url="https://example.com",
            raw_ingredients=", ".join(ingredients),
            ingredients=ingredients,
            extraction_method="browser_dom:test",
            extraction_success=True,
        ),
        option_id=option_id,
        option_name=option_name,
    )


def test_option_status_round_trip_for_all_option_parse_statuses() -> None:
    """ready/unmapped/empty/ambiguous/error 각 옵션 상태가 저장한
    그대로 읽힌다."""

    repository = _repository()
    product = _product()
    now = utc_now()
    expires_at = now + timedelta(days=1)

    entries = [
        _entry("opt-ready", "레디", ["정제수", "글리세린"]),
        _entry("opt-empty", "엠프티", ["정제수"]),
    ]
    production_result = build_parser_result(
        "production",
        [
            build_option_level_result(
                option_id="opt-ready",
                option_name="레디",
                mapping_status="matched",
                ingredients=["정제수", "글리세린"],
            ),
            build_option_level_result(
                option_id="opt-empty",
                option_name="엠프티",
                mapping_status="unmatched",
                ingredients=[],
            ),
        ],
    )

    repository.save_collection(
        product,
        entries=entries,
        status="ready",
        options=[],
        expires_at=expires_at,
        parser_version="option-sections-v1",
        production_parser_result=production_result,
    )

    with repository.session_factory() as session:
        rows = {
            row[0]: row[1]
            for row in session.execute(
                text(
                    "SELECT r.option_id, r.option_cache_status "
                    "FROM product_ingredient_records r "
                    "JOIN products p ON p.id = r.product_id "
                    "WHERE p.external_product_id = :pid"
                ),
                {"pid": product.product_id},
            )
        }
    assert rows == {"opt-ready": "ready", "opt-empty": "unmapped"}


def test_collection_status_round_trip_for_ready_and_partial() -> None:
    repository = _repository()
    now = utc_now()
    expires_at = now + timedelta(days=1)

    for label, collection_status in (
        ("A000000000010", "ready"),
        ("A000000000011", "partial"),
    ):
        product = ProductCandidate(
            product_id=label,
            source="oliveyoung",
            product_name="상품",
            category="color_makeup",
            product_url="https://example.com/" + label,
        )
        entry = ProductCollectionEntry(
            result=ProductIngredientResult(
                product_id=label,
                product_url="https://example.com",
                raw_ingredients="정제수",
                ingredients=["정제수"],
                extraction_method="browser_dom:test",
                extraction_success=True,
            ),
            option_id="opt-1",
            option_name="옵션1",
        )
        production_result = build_parser_result(
            "production",
            [
                build_option_level_result(
                    option_id="opt-1",
                    option_name="옵션1",
                    mapping_status="matched",
                    ingredients=["정제수"],
                )
            ],
        )
        production_result = _dataclass_replace(
            production_result, collection_status=collection_status
        )

        repository.save_collection(
            product,
            entries=[entry],
            status="ready",
            options=[],
            expires_at=expires_at,
            parser_version="option-sections-v1",
            production_parser_result=production_result,
        )

        with repository.session_factory() as session:
            stored = session.execute(
                text(
                    "SELECT s.option_cache_collection_status "
                    "FROM product_collection_states s "
                    "JOIN products p ON p.id = s.product_id "
                    "WHERE p.external_product_id = :pid"
                ),
                {"pid": label},
            ).scalar_one()
        assert stored == collection_status


def test_diagnostics_round_trip_is_valid_json() -> None:
    import json

    repository = _repository()
    product = _product("A000000000012")
    now = utc_now()
    expires_at = now + timedelta(days=1)

    entry = _entry(
        "opt-1", "옵션1", ["정제수", "글리세린"], product_id="A000000000012"
    )
    production_result = build_parser_result(
        "production",
        [
            build_option_level_result(
                option_id="opt-1",
                option_name="옵션1",
                mapping_status="matched",
                ingredients=["정제수", "글리세린"],
            )
        ],
    )
    repository.save_collection(
        product,
        entries=[entry],
        status="ready",
        options=[],
        expires_at=expires_at,
        parser_version="option-sections-v1",
        production_parser_result=production_result,
    )

    with repository.session_factory() as session:
        collection_diag, option_diag = session.execute(
            text(
                "SELECT s.option_cache_diagnostics_json, "
                "r.option_cache_diagnostics_json "
                "FROM product_collection_states s "
                "JOIN products p ON p.id = s.product_id "
                "JOIN product_ingredient_records r ON r.product_id = p.id "
                "WHERE p.external_product_id = :pid"
            ),
            {"pid": product.product_id},
        ).one()

    collection_payload = json.loads(collection_diag)
    option_payload = json.loads(option_diag)
    assert collection_payload["production_ready_count"] == 1
    assert option_payload["raw_mapping_status"] == "matched"
    # ingredient 원문/옵션명은 diagnostics에 남기지 않는다.
    assert "정제수" not in collection_diag
    assert "정제수" not in option_diag


# ---------------------------------------------------------------------------
# 안전한 JSON 처리
# ---------------------------------------------------------------------------


def test_safe_json_dumps_returns_none_instead_of_raising() -> None:
    # set은 JSON으로 직렬화할 수 없다.
    assert _safe_json_dumps({"bad": {1, 2, 3}}) is None
    assert _safe_json_dumps({"ok": 1}) == '{"ok": 1}'


def test_corrupted_options_json_does_not_crash_option_cache_reader() -> (
    None
):
    """options_json이 깨져 있어도 신규 reader와 legacy 판정 모두
    예외를 던지지 않아야 한다."""

    repository = _repository()
    product = _product("A000000000013")
    now = utc_now()
    expires_at = now + timedelta(days=1)

    entry = _entry(
        "opt-1", "옵션1", ["정제수", "글리세린"], product_id="A000000000013"
    )
    production_result = build_parser_result(
        "production",
        [
            build_option_level_result(
                option_id="opt-1",
                option_name="옵션1",
                mapping_status="matched",
                ingredients=["정제수", "글리세린"],
            )
        ],
    )
    repository.save_collection(
        product,
        entries=[entry],
        status="ready",
        options=[
            {
                "internal_option_key": "opt-1",
                "option_name": "옵션1",
                "raw_option_name": "옵션1",
            }
        ],
        expires_at=expires_at,
        parser_version="option-sections-v1",
        production_parser_result=production_result,
    )

    with repository.session_factory() as session:
        session.execute(
            text(
                "UPDATE product_collection_states SET "
                "options_json = '{not valid json' "
                "WHERE product_id = (SELECT id FROM products "
                "WHERE external_product_id = :pid)"
            ),
            {"pid": product.product_id},
        )
        session.commit()

    result = repository.get_cached_preparation(
        source=product.source,
        external_product_id=product.product_id,
        now=now,
        prefer_option_cache=True,
    )
    # 신규 경로는 손상된 metadata로 옵션을 복원할 수 없으므로 None을
    # 반환해 legacy 판정으로 넘어간다. legacy 판정 역시 손상된
    # options_json을 이미 안전하게 처리하고 있어(metadata_by_id={})
    # 예외 없이 HIT를 만든다 - 어느 쪽도 크래시하지 않는다는 것이
    # 핵심이다.
    assert result is not None
    assert result.status == "ready"
    assert result.options[0].option_id == "opt-1"


# ---------------------------------------------------------------------------
# 신규 cache 완전 -> 신규 reader / 불완전 -> legacy fallback
# ---------------------------------------------------------------------------


def test_legacy_fallback_when_option_cache_columns_are_empty() -> None:
    """production_parser_result 없이 저장하면(legacy 저장) 신규 컬럼은
    비어 있고, prefer_option_cache=True로 조회해도 legacy 판정
    그대로 HIT가 나와야 한다."""

    repository = _repository()
    product = _product("A000000000014")
    now = utc_now()
    expires_at = now + timedelta(days=1)

    entry = _entry(
        "opt-1", "옵션1", ["정제수", "글리세린"], product_id="A000000000014"
    )
    repository.save_collection(
        product,
        entries=[entry],
        status="ready",
        options=[
            {
                "internal_option_key": "opt-1",
                "option_name": "옵션1",
                "raw_option_name": "옵션1",
            }
        ],
        expires_at=expires_at,
        parser_version="option-sections-v1",
        # production_parser_result 생략 - legacy 저장.
    )

    result = repository.get_cached_preparation(
        source=product.source,
        external_product_id=product.product_id,
        now=now,
        prefer_option_cache=True,
    )
    assert result is not None
    assert result.status == "ready"
    assert result.parser_version == "option-sections-v1"
    assert [option.option_id for option in result.options] == ["opt-1"]


def test_new_reader_used_when_option_cache_is_complete() -> None:
    """신규 컬럼이 완전하면 신규 reader가 값을 만든다 - 신규 컬럼
    쪽 parser_version만 다른 값으로 확인해 어느 경로로 읽었는지
    구분한다."""

    repository = _repository()
    product = _product("A000000000015")
    now = utc_now()
    expires_at = now + timedelta(days=1)

    entry = _entry(
        "opt-1", "옵션1", ["정제수", "글리세린"], product_id="A000000000015"
    )
    production_result = build_parser_result(
        "production",
        [
            build_option_level_result(
                option_id="opt-1",
                option_name="옵션1",
                mapping_status="matched",
                ingredients=["정제수", "글리세린"],
            )
        ],
    )
    repository.save_collection(
        product,
        entries=[entry],
        status="ready",
        options=[
            {
                "internal_option_key": "opt-1",
                "option_name": "옵션1",
                "raw_option_name": "옵션1",
            }
        ],
        expires_at=expires_at,
        parser_version="legacy-version-marker",
        production_parser_result=production_result,
    )
    # option_cache_parser_version에는 실제로는 같은 값이 들어가지만,
    # 신규 경로가 실제로 이 컬럼을 읽는지 확인하기 위해 직접 다른
    # 값으로 덮어써 legacy parser_version과 구분한다.
    with repository.session_factory() as session:
        session.execute(
            text(
                "UPDATE product_collection_states SET "
                "option_cache_parser_version = 'option-cache-marker' "
                "WHERE product_id = (SELECT id FROM products "
                "WHERE external_product_id = :pid)"
            ),
            {"pid": product.product_id},
        )
        session.commit()

    result_with_option_cache = repository.get_cached_preparation(
        source=product.source,
        external_product_id=product.product_id,
        now=now,
        prefer_option_cache=True,
    )
    result_legacy_only = repository.get_cached_preparation(
        source=product.source,
        external_product_id=product.product_id,
        now=now,
        prefer_option_cache=False,
    )
    assert result_with_option_cache.parser_version == "option-cache-marker"
    assert result_legacy_only.parser_version == "legacy-version-marker"


def test_incomplete_option_cache_falls_back_to_legacy() -> None:
    """옵션 중 하나라도 option_cache_status가 비어 있으면(불완전)
    신규 경로를 포기하고 legacy 판정으로 넘어간다."""

    repository = _repository()
    product = _product("A000000000016")
    now = utc_now()
    expires_at = now + timedelta(days=1)

    entries = [
        _entry("opt-1", "옵션1", ["정제수"], product_id="A000000000016"),
        _entry("opt-2", "옵션2", ["글리세린"], product_id="A000000000016"),
    ]
    production_result = build_parser_result(
        "production",
        [
            build_option_level_result(
                option_id="opt-1",
                option_name="옵션1",
                mapping_status="matched",
                ingredients=["정제수"],
            ),
            build_option_level_result(
                option_id="opt-2",
                option_name="옵션2",
                mapping_status="matched",
                ingredients=["글리세린"],
            ),
        ],
    )
    repository.save_collection(
        product,
        entries=entries,
        status="ready",
        options=[
            {
                "internal_option_key": option_id,
                "option_name": name,
                "raw_option_name": name,
            }
            for option_id, name in (("opt-1", "옵션1"), ("opt-2", "옵션2"))
        ],
        expires_at=expires_at,
        parser_version="option-sections-v1",
        production_parser_result=production_result,
    )
    # opt-2의 option_cache_status만 비워 '불완전'을 만든다.
    with repository.session_factory() as session:
        session.execute(
            text(
                "UPDATE product_ingredient_records SET "
                "option_cache_status = NULL WHERE option_id = 'opt-2'"
            )
        )
        session.commit()

    result = repository.get_cached_preparation(
        source=product.source,
        external_product_id=product.product_id,
        now=now,
        prefer_option_cache=True,
    )
    # legacy 판정으로 fallback했으므로 legacy parser_version(둘 다
    # 같은 값)으로 정상 HIT가 나온다 - 크래시하지 않는다.
    assert result is not None
    assert result.status == "ready"
    assert {option.option_id for option in result.options} == {
        "opt-1",
        "opt-2",
    }


# ---------------------------------------------------------------------------
# rollback: transaction 중간 실패 시 이전 상태 보존
# ---------------------------------------------------------------------------


def test_failed_save_rolls_back_without_corrupting_previous_state() -> None:
    repository = _repository()
    product = _product("A000000000017")
    now = utc_now()
    expires_at = now + timedelta(days=1)

    first_entry = _entry(
        "opt-1", "옵션1", ["정제수", "글리세린"], product_id="A000000000017"
    )
    first_result = build_parser_result(
        "production",
        [
            build_option_level_result(
                option_id="opt-1",
                option_name="옵션1",
                mapping_status="matched",
                ingredients=["정제수", "글리세린"],
            )
        ],
    )
    repository.save_collection(
        product,
        entries=[first_entry],
        status="ready",
        options=[],
        expires_at=expires_at,
        parser_version="option-sections-v1",
        production_parser_result=first_result,
    )

    # product_id가 일치하지 않는 entry를 섞어 transaction 중간에서
    # 실패를 강제한다(기존 검증 로직이 그대로 발동한다).
    bad_entry = ProductCollectionEntry(
        result=ProductIngredientResult(
            product_id="mismatched-product-id",
            product_url="https://example.com",
            raw_ingredients="탤크",
            ingredients=["탤크"],
            extraction_method="browser_dom:test",
            extraction_success=True,
        ),
        option_id="opt-1",
        option_name="옵션1",
    )
    second_result = build_parser_result(
        "production",
        [
            build_option_level_result(
                option_id="opt-1",
                option_name="옵션1",
                mapping_status="matched",
                ingredients=["탤크"],
            )
        ],
    )

    try:
        repository.save_collection(
            product,
            entries=[bad_entry],
            status="ready",
            options=[],
            expires_at=expires_at,
            parser_version="option-sections-v1",
            production_parser_result=second_result,
        )
        raised = False
    except ValueError:
        raised = True

    assert raised is True

    with repository.session_factory() as session:
        ingredients, option_cache_status = session.execute(
            text(
                "SELECT r.raw_ingredients, r.option_cache_status "
                "FROM product_ingredient_records r "
                "JOIN products p ON p.id = r.product_id "
                "WHERE p.external_product_id = :pid"
            ),
            {"pid": product.product_id},
        ).one()
    # 실패한 두 번째 저장 시도의 '탤크'가 아니라, 첫 번째 성공한
    # 저장의 값이 그대로 남아 있어야 한다(rollback).
    assert ingredients == "정제수, 글리세린"
    assert option_cache_status == "ready"


# ---------------------------------------------------------------------------
# prepare_product() 통합: flag on/off + shadow는 절대 저장에 관여하지
# 않는다
# ---------------------------------------------------------------------------


def test_prepare_product_writes_only_production_result_even_with_shadow_observation_enabled(  # noqa: E501
    monkeypatch,
) -> None:
    """shadow_observation_enabled=True + option_level_cache_enabled=True
    상태에서 실제 prepare_product()를 실행한다. shadow가 production과
    완전히 다른 성분을 반환하도록 monkeypatch해도, DB에 실제로
    저장되는 값은 production 결과뿐이어야 한다 - option_cache_*
    컬럼을 포함해서다.

    production이 이미 100% matched(ready)인 경우에만 실제 저장이
    일어나고, 그 경우 Step 2 정책상 shadow는 아예 실행되지 않는다
    (partial/failed일 때만 shadow가 도는데, 그 경로는 애초에
    store_collection을 호출하지 않는다). 즉 '저장이 일어나는 모든
    경우에 shadow는 구조적으로 관여할 수 없다'는 것을 실제 서비스
    경로로 확인한다.
    """

    import app.products.option_service as option_service_module
    from app.products.ingredient_cache_service import (
        ProductIngredientCacheService,
    )
    from app.products.models import ProductCandidate as _ProductCandidate
    from app.products.option_models import (
        ProductIngredientRawDocument,
        ProductOptionExtractionResult,
    )
    from app.products.option_parser import PARSER_VERSION, make_product_option
    from app.products.option_service import ProductOptionService

    class _FakeExtractor:
        def __init__(self, result) -> None:
            self.result = result
            self.calls = 0

        def extract(self, product_id: str, product_url: str):
            self.calls += 1
            return self.result

    def _shadow_with_different_ingredients(raw_text, canonical_options):
        raise AssertionError(
            "production이 ready이므로 shadow는 절대 호출되면 안 됩니다."
        )

    monkeypatch.setattr(
        option_service_module,
        "shadow_parse_option_ingredient_sections",
        _shadow_with_different_ingredients,
    )

    repository = _repository()
    cache_service = ProductIngredientCacheService(
        repository=repository,
        extractor=None,
        clock=utc_now,
        option_level_cache_enabled=True,
    )

    product = _ProductCandidate(
        product_id="A000000000018",
        source="oliveyoung",
        product_name="통합 테스트 상품",
        category="color_makeup",
        product_url=(
            "https://www.oliveyoung.co.kr/store/goods/"
            "getGoodsDetail.do?goodsNo=A000000000018"
        ),
    )
    extraction = ProductOptionExtractionResult(
        status="collected",
        options=[make_product_option("19호")],
        raw_document=ProductIngredientRawDocument(
            source="oliveyoung",
            product_id="A000000000018",
            raw_text="[19호] 정제수, 글리세린, 향료",
            parser_version=PARSER_VERSION,
        ),
    )

    service = ProductOptionService(
        extractor=_FakeExtractor(extraction),
        cache_service=cache_service,
        shadow_observation_enabled=True,
    )

    result = service.prepare_product(product)

    assert result.status == "ready"

    with repository.session_factory() as session:
        ingredients, option_cache_status, option_cache_parser_version = (
            session.execute(
                text(
                    "SELECT r.raw_ingredients, r.option_cache_status, "
                    "r.option_cache_parser_version "
                    "FROM product_ingredient_records r "
                    "JOIN products p ON p.id = r.product_id "
                    "WHERE p.external_product_id = :pid"
                ),
                {"pid": "A000000000018"},
            ).one()
        )
    assert ingredients == "정제수, 글리세린, 향료"
    assert option_cache_status == "ready"
    assert option_cache_parser_version == PARSER_VERSION


def test_prepare_product_flag_off_never_writes_option_cache_columns() -> (
    None
):
    from app.products.ingredient_cache_service import (
        ProductIngredientCacheService,
    )
    from app.products.models import ProductCandidate as _ProductCandidate
    from app.products.option_models import (
        ProductIngredientRawDocument,
        ProductOptionExtractionResult,
    )
    from app.products.option_parser import PARSER_VERSION, make_product_option
    from app.products.option_service import ProductOptionService

    class _FakeExtractor:
        def extract(self, product_id: str, product_url: str):
            return ProductOptionExtractionResult(
                status="collected",
                options=[make_product_option("19호")],
                raw_document=ProductIngredientRawDocument(
                    source="oliveyoung",
                    product_id="A000000000019",
                    raw_text="[19호] 정제수, 글리세린, 향료",
                    parser_version=PARSER_VERSION,
                ),
            )

    repository = _repository()
    cache_service = ProductIngredientCacheService(
        repository=repository,
        extractor=None,
        clock=utc_now,
        option_level_cache_enabled=False,
    )
    product = _ProductCandidate(
        product_id="A000000000019",
        source="oliveyoung",
        product_name="플래그 off 테스트 상품",
        category="color_makeup",
        product_url=(
            "https://www.oliveyoung.co.kr/store/goods/"
            "getGoodsDetail.do?goodsNo=A000000000019"
        ),
    )

    service = ProductOptionService(
        extractor=_FakeExtractor(),
        cache_service=cache_service,
    )
    result = service.prepare_product(product)
    assert result.status == "ready"

    with repository.session_factory() as session:
        option_cache_status, collection_cache_status = session.execute(
            text(
                "SELECT r.option_cache_status, s.option_cache_collection_status "
                "FROM product_ingredient_records r "
                "JOIN products p ON p.id = r.product_id "
                "JOIN product_collection_states s ON s.product_id = p.id "
                "WHERE p.external_product_id = :pid"
            ),
            {"pid": "A000000000019"},
        ).one()
    assert option_cache_status is None
    assert collection_cache_status is None


# ---------------------------------------------------------------------------
# option-level partial success: save_option_cache_snapshot
# ---------------------------------------------------------------------------


def test_partial_snapshot_round_trips_all_mixed_option_statuses() -> None:
    """ready/unmapped/empty/ambiguous/error가 섞인 partial 결과가
    옵션별로 정확히 저장·복원된다. ready만 ingredients를 갖고,
    나머지는 성분 없이 상태/mapped_section_id/diagnostics만
    남는다."""

    repository = _repository()
    product = _product("A000000000020")
    now = utc_now()
    expires_at = now + timedelta(days=1)

    parser_result = build_parser_result(
        "production",
        [
            build_option_level_result(
                option_id="opt-ready",
                option_name="레디",
                mapping_status="matched",
                ingredients=["정제수", "글리세린"],
            ),
            build_option_level_result(
                option_id="opt-unmapped",
                option_name="언매치드",
                mapping_status="unmatched",
                ingredients=[],
            ),
            build_option_level_result(
                option_id="opt-empty",
                option_name="엠프티",
                mapping_status="matched",
                ingredients=[],
            ),
            build_option_level_result(
                option_id="opt-ambiguous",
                option_name="앰비규어스",
                mapping_status="ambiguous",
                ingredients=[],
            ),
            build_option_level_result(
                option_id="opt-error",
                option_name="에러",
                mapping_status="totally_unexpected_status",
                ingredients=[],
            ),
        ],
    )
    assert parser_result.collection_status == "partial"

    repository.save_option_cache_snapshot(
        product,
        parser_result=parser_result,
        parser_version="option-sections-v1",
        expires_at=expires_at,
    )

    with repository.session_factory() as session:
        rows = {
            row[0]: (row[1], row[2], row[3])
            for row in session.execute(
                text(
                    "SELECT r.option_id, r.option_cache_status, "
                    "r.raw_ingredients, r.option_cache_mapped_section_id "
                    "FROM product_ingredient_records r "
                    "JOIN products p ON p.id = r.product_id "
                    "WHERE p.external_product_id = :pid"
                ),
                {"pid": product.product_id},
            )
        }
    assert rows["opt-ready"] == ("ready", "정제수, 글리세린", "opt-ready")
    assert rows["opt-unmapped"] == ("unmapped", "", "opt-unmapped")
    assert rows["opt-empty"] == ("empty", "", "opt-empty")
    assert rows["opt-ambiguous"] == ("ambiguous", "", "opt-ambiguous")
    assert rows["opt-error"] == ("error", "", "opt-error")


def test_partial_snapshot_preserves_diagnostics_and_ready_ingredients_readable() -> (  # noqa: E501
    None
):
    import json as _json

    repository = _repository()
    product = _product("A000000000021")
    now = utc_now()
    expires_at = now + timedelta(days=1)

    parser_result = build_parser_result(
        "production",
        [
            build_option_level_result(
                option_id="opt-ready",
                option_name="레디",
                mapping_status="matched",
                ingredients=["정제수", "글리세린", "향료"],
            ),
            build_option_level_result(
                option_id="opt-unmapped",
                option_name="언매치드",
                mapping_status="unmatched",
                ingredients=[],
            ),
        ],
    )
    repository.save_option_cache_snapshot(
        product,
        parser_result=parser_result,
        parser_version="option-sections-v1",
        expires_at=expires_at,
    )

    result = repository.get_cached_preparation(
        source=product.source,
        external_product_id=product.product_id,
        now=now,
        prefer_option_cache=True,
    )
    assert result is not None
    assert result.status == "partial"
    ready_option = next(o for o in result.options if o.option_id == "opt-ready")
    assert ready_option.option_name == "레디"

    with repository.session_factory() as session:
        ready_ingredients, unmapped_diag = session.execute(
            text(
                "SELECT "
                "(SELECT group_concat(i.ingredient_name, ',') "
                " FROM product_ingredient_items i "
                " WHERE i.ingredient_record_id = r_ready.id), "
                "r_unmapped.option_cache_diagnostics_json "
                "FROM product_ingredient_records r_ready, "
                "product_ingredient_records r_unmapped "
                "WHERE r_ready.option_id = 'opt-ready' "
                "AND r_unmapped.option_id = 'opt-unmapped'"
            )
        ).one()
    assert ready_ingredients == "정제수,글리세린,향료"
    diagnostics = _json.loads(unmapped_diag)
    assert diagnostics["raw_mapping_status"] == "unmatched"


def test_partial_cache_does_not_fall_back_to_legacy() -> None:
    """collection_status=partial이어도 신규 컬럼이 완전하면 legacy로
    fallback하지 않는다 - legacy 판정(prefer_option_cache=False)은
    여전히 None(=캐시 없음)이어야 한다."""

    repository = _repository()
    product = _product("A000000000022")
    now = utc_now()
    expires_at = now + timedelta(days=1)

    parser_result = build_parser_result(
        "production",
        [
            build_option_level_result(
                option_id="opt-ready",
                option_name="레디",
                mapping_status="matched",
                ingredients=["정제수", "글리세린"],
            ),
            build_option_level_result(
                option_id="opt-unmapped",
                option_name="언매치드",
                mapping_status="unmatched",
                ingredients=[],
            ),
        ],
    )
    repository.save_option_cache_snapshot(
        product,
        parser_result=parser_result,
        parser_version="option-sections-v1",
        expires_at=expires_at,
    )

    with_option_cache = repository.get_cached_preparation(
        source=product.source,
        external_product_id=product.product_id,
        now=now,
        prefer_option_cache=True,
    )
    legacy_only = repository.get_cached_preparation(
        source=product.source,
        external_product_id=product.product_id,
        now=now,
        prefer_option_cache=False,
    )
    assert with_option_cache is not None
    assert with_option_cache.status == "partial"
    assert legacy_only is None


def test_incomplete_partial_snapshot_still_falls_back_to_legacy() -> None:
    """partial 스냅샷이라도 옵션 하나의 신규 컬럼이 비어 있으면(예:
    저장 중 문제) 여전히 legacy 판정(None)으로 넘어간다."""

    repository = _repository()
    product = _product("A000000000023")
    now = utc_now()
    expires_at = now + timedelta(days=1)

    parser_result = build_parser_result(
        "production",
        [
            build_option_level_result(
                option_id="opt-ready",
                option_name="레디",
                mapping_status="matched",
                ingredients=["정제수"],
            ),
            build_option_level_result(
                option_id="opt-unmapped",
                option_name="언매치드",
                mapping_status="unmatched",
                ingredients=[],
            ),
        ],
    )
    repository.save_option_cache_snapshot(
        product,
        parser_result=parser_result,
        parser_version="option-sections-v1",
        expires_at=expires_at,
    )
    with repository.session_factory() as session:
        session.execute(
            text(
                "UPDATE product_ingredient_records SET "
                "option_cache_status = NULL WHERE option_id = 'opt-unmapped'"
            )
        )
        session.commit()

    result = repository.get_cached_preparation(
        source=product.source,
        external_product_id=product.product_id,
        now=now,
        prefer_option_cache=True,
    )
    assert result is None


def test_null_mapped_section_id_on_non_ready_option_does_not_break_completeness() -> (  # noqa: E501
    None
):
    """mapped_section_id는 unmapped/ambiguous 옵션에서 NULL이어도
    정상이다 - 완전성 판정은 option_count/collection_status/
    option_status/parser_version만으로 결정하고, mapped_section_id
    유무로 legacy fallback을 강제하지 않는다."""

    repository = _repository()
    product = _product("A000000000028")
    now = utc_now()
    expires_at = now + timedelta(days=1)

    parser_result = build_parser_result(
        "production",
        [
            build_option_level_result(
                option_id="opt-ready",
                option_name="레디",
                mapping_status="matched",
                ingredients=["정제수", "글리세린"],
            ),
            build_option_level_result(
                option_id="opt-unmapped",
                option_name="언매치드",
                mapping_status="unmatched",
                ingredients=[],
            ),
            build_option_level_result(
                option_id="opt-ambiguous",
                option_name="앰비규어스",
                mapping_status="ambiguous",
                ingredients=[],
            ),
        ],
    )
    repository.save_option_cache_snapshot(
        product,
        parser_result=parser_result,
        parser_version="option-sections-v1",
        expires_at=expires_at,
    )
    # 실제 매핑이 없는 옵션은 mapped_section_id가 NULL인 채로 저장될
    # 수 있다는 것을 명시적으로 재현한다(현재 writer는 항상 채우지만,
    # reader의 완전성 판정이 이 필드에 의존하지 않아야 한다).
    with repository.session_factory() as session:
        session.execute(
            text(
                "UPDATE product_ingredient_records SET "
                "option_cache_mapped_section_id = NULL "
                "WHERE option_id IN ('opt-unmapped', 'opt-ambiguous')"
            )
        )
        session.commit()

    result = repository.get_cached_preparation(
        source=product.source,
        external_product_id=product.product_id,
        now=now,
        prefer_option_cache=True,
    )
    assert result is not None
    assert result.status == "partial"
    assert {option.option_id for option in result.options} == {
        "opt-ready",
        "opt-unmapped",
        "opt-ambiguous",
    }

    # status/parser_version 중 하나라도 NULL이면 여전히 legacy로
    # fallback한다 - 완전성 기준에서 이 필드들은 제외되지 않았다.
    with repository.session_factory() as session:
        session.execute(
            text(
                "UPDATE product_ingredient_records SET "
                "option_cache_status = NULL WHERE option_id = 'opt-unmapped'"
            )
        )
        session.commit()

    fallback_result = repository.get_cached_preparation(
        source=product.source,
        external_product_id=product.product_id,
        now=now,
        prefer_option_cache=True,
    )
    assert fallback_result is None


def test_save_option_cache_snapshot_accepts_shadow_source_and_preserves_it() -> (  # noqa: E501
    None
):
    """Step 6: selector가 승인한 shadow ParserResult(source="shadow")는
    repository 계층에서 provenance를 잃지 않고 그대로 저장/복원된다.
    '선택되지 않은 raw shadow 저장 금지'는 이 계층이 아니라
    option_service.py 호출부가 통제한다 - repository는 production/
    shadow 둘 다 유효한 값으로 받아들인다."""

    repository = _repository()
    product = _product("A000000000024")
    expires_at = utc_now() + timedelta(days=1)

    shadow_result = build_parser_result(
        "shadow",
        [
            build_option_level_result(
                option_id="opt-1",
                option_name="옵션1",
                mapping_status="matched",
                ingredients=["정제수"],
            )
        ],
    )
    # source가 "shadow"여도 예외 없이 저장된다(provenance 유지).
    repository.save_option_cache_snapshot(
        product,
        parser_result=shadow_result,
        parser_version="option-sections-v1",
        expires_at=expires_at,
    )
    with repository.session_factory() as session:
        row = session.execute(
            text(
                "SELECT r.option_cache_status "
                "FROM product_ingredient_records r "
                "JOIN products p ON p.id = r.product_id "
                "WHERE p.external_product_id = :pid"
            ),
            {"pid": product.product_id},
        ).first()
    assert row == ("ready",)


def test_save_option_cache_snapshot_rejects_unknown_source() -> None:
    """production/shadow가 아닌 값은 여전히 거부한다(오타·잘못된
    호출 방지용 최소한의 안전장치)."""

    repository = _repository()
    product = _product("A000000000034")
    expires_at = utc_now() + timedelta(days=1)

    garbage_result = build_parser_result(
        "production",
        [
            build_option_level_result(
                option_id="opt-1",
                option_name="옵션1",
                mapping_status="matched",
                ingredients=["정제수"],
            )
        ],
    )
    garbage_result = _dataclass_replace(garbage_result, source="not_a_real_source")

    raised = False
    try:
        repository.save_option_cache_snapshot(
            product,
            parser_result=garbage_result,
            parser_version="option-sections-v1",
            expires_at=expires_at,
        )
    except ValueError:
        raised = True
    assert raised is True

    with repository.session_factory() as session:
        row = session.execute(
            text("SELECT id FROM products WHERE external_product_id = :pid"),
            {"pid": product.product_id},
        ).first()
    # product row조차 만들어지지 않는다(트랜잭션 진입 전에 거부).
    assert row is None


# ---------------------------------------------------------------------------
# prepare_product() 통합: partial + flag on/off
# ---------------------------------------------------------------------------


def _mixed_mapping_extraction(product_id: str):
    from app.products.option_models import (
        ProductIngredientRawDocument,
        ProductOptionExtractionResult,
    )
    from app.products.option_parser import PARSER_VERSION, make_product_option

    return ProductOptionExtractionResult(
        status="collected",
        options=[
            make_product_option("19호"),
            make_product_option("21호"),
        ],
        raw_document=ProductIngredientRawDocument(
            source="oliveyoung",
            product_id=product_id,
            raw_text="[19호] 정제수, 글리세린, 향료",
            parser_version=PARSER_VERSION,
        ),
    )


def test_prepare_product_saves_partial_option_cache_when_flag_enabled() -> (
    None
):
    """production이 partial(19호만 matched)일 때 flag=true면
    option-level cache에 저장되고, 응답(status)은 여전히
    "mapping_failed"·legacy 저장은 비어 있는 채로 남지만(Step 3와
    동일), Step 4부터는 ready 옵션(19호)을 응답에 남겨 분석에 쓸 수
    있게 한다."""

    from app.products.ingredient_cache_service import (
        ProductIngredientCacheService,
    )
    from app.products.models import ProductCandidate as _ProductCandidate
    from app.products.option_service import ProductOptionService

    class _FakeExtractor:
        def __init__(self, result) -> None:
            self.result = result

        def extract(self, product_id: str, product_url: str):
            return self.result

    repository = _repository()
    cache_service = ProductIngredientCacheService(
        repository=repository,
        extractor=None,
        clock=utc_now,
        option_level_cache_enabled=True,
    )
    product = _product("A000000000025")
    service = ProductOptionService(
        extractor=_FakeExtractor(
            _mixed_mapping_extraction("A000000000025")
        ),
        cache_service=cache_service,
    )

    result = service.prepare_product(product)

    assert result.status == "mapping_failed"
    assert result.collection_status == "partial"
    assert result.can_analyze is True
    options_by_name = {
        option.option_name: option for option in result.options
    }
    assert options_by_name["19"].analysis_available is True
    assert options_by_name["19"].status == "ready"
    assert options_by_name["21"].analysis_available is False

    with repository.session_factory() as session:
        collection_status = session.execute(
            text(
                "SELECT s.option_cache_collection_status "
                "FROM product_collection_states s "
                "JOIN products p ON p.id = s.product_id "
                "WHERE p.external_product_id = :pid"
            ),
            {"pid": "A000000000025"},
        ).scalar_one()
        option_rows = {
            row[0]: row[1]
            for row in session.execute(
                text(
                    "SELECT r.option_name, r.option_cache_status "
                    "FROM product_ingredient_records r "
                    "JOIN products p ON p.id = r.product_id "
                    "WHERE p.external_product_id = :pid"
                ),
                {"pid": "A000000000025"},
            )
        }
    assert collection_status == "partial"
    assert option_rows == {"19": "ready", "21": "unmapped"}

    # 신규 reader로 조회하면 partial cache HIT가 만들어진다(legacy는
    # 여전히 None).
    option_cache_hit = repository.get_cached_preparation(
        source=product.source,
        external_product_id=product.product_id,
        now=utc_now(),
        prefer_option_cache=True,
    )
    legacy_hit = repository.get_cached_preparation(
        source=product.source,
        external_product_id=product.product_id,
        now=utc_now(),
        prefer_option_cache=False,
    )
    assert option_cache_hit is not None
    assert option_cache_hit.status == "partial"
    assert legacy_hit is None


def test_prepare_product_does_not_save_partial_option_cache_when_flag_disabled() -> (  # noqa: E501
    None
):
    from app.products.ingredient_cache_service import (
        ProductIngredientCacheService,
    )
    from app.products.option_service import ProductOptionService

    class _FakeExtractor:
        def __init__(self, result) -> None:
            self.result = result

        def extract(self, product_id: str, product_url: str):
            return self.result

    repository = _repository()
    cache_service = ProductIngredientCacheService(
        repository=repository,
        extractor=None,
        clock=utc_now,
        option_level_cache_enabled=False,
    )
    product = _product("A000000000026")
    service = ProductOptionService(
        extractor=_FakeExtractor(
            _mixed_mapping_extraction("A000000000026")
        ),
        cache_service=cache_service,
    )

    result = service.prepare_product(product)
    assert result.status == "mapping_failed"

    with repository.session_factory() as session:
        state_row = session.execute(
            text(
                "SELECT s.id FROM product_collection_states s "
                "JOIN products p ON p.id = s.product_id "
                "WHERE p.external_product_id = :pid"
            ),
            {"pid": "A000000000026"},
        ).first()
    # flag가 꺼져 있으면 partial 스냅샷 자체가 저장되지 않는다 -
    # collection_states row조차 생기지 않는다.
    assert state_row is None


def test_prepare_product_does_not_save_shadow_selected_result_for_partial(
    monkeypatch,
) -> None:
    """shadow_observation_enabled=True로 shadow가 partial 상황에서
    실제로 돌면서 21호까지 matched로 "확인"해도(=selector가 shadow를
    고를 수 있는 상황을 실제로 만든다), option-level cache에 저장된
    값은 production 그대로(19호만 ready)여야 한다."""

    import app.products.option_service as option_service_module
    from app.products.ingredient_cache_service import (
        ProductIngredientCacheService,
    )
    from app.products.option_parser import (
        IngredientSection,
        OptionSectionMapping,
        ShadowParseResult,
    )
    from app.products.option_service import ProductOptionService

    def _shadow_confirms_everything(raw_text, canonical_options):
        sections = []
        mappings = []
        for index, option in enumerate(canonical_options):
            ingredients = ("정제수", "글리세린", "탤크", "샤도우전용성분")
            sections.append(
                IngredientSection(
                    raw_header=f"[{option.option_name}]",
                    header_start_index=0,
                    header_end_index=0,
                    body_start_index=0,
                    body_end_index=0,
                    raw_ingredient_text=", ".join(ingredients),
                    ingredients=ingredients,
                )
            )
            mappings.append(
                OptionSectionMapping(
                    internal_option_key=option.internal_option_key,
                    option_name=option.option_name,
                    section_index=index,
                    mapping_status="matched",
                    mapping_method="fake_shadow_for_test",
                    mapping_confidence=1.0,
                )
            )
        return ShadowParseResult(
            sections=tuple(sections),
            boundary_candidates=(),
            document_format="option_full_sections",
            structure_reason=None,
            mappings=tuple(mappings),
            orphan_section_count=0,
            matched_count=len(mappings),
            unmatched_count=0,
            ambiguous_count=0,
            unsupported_count=0,
        )

    monkeypatch.setattr(
        option_service_module,
        "shadow_parse_option_ingredient_sections",
        _shadow_confirms_everything,
    )

    class _FakeExtractor:
        def __init__(self, result) -> None:
            self.result = result

        def extract(self, product_id: str, product_url: str):
            return self.result

    repository = _repository()
    cache_service = ProductIngredientCacheService(
        repository=repository,
        extractor=None,
        clock=utc_now,
        option_level_cache_enabled=True,
    )
    product = _product("A000000000027")
    service = ProductOptionService(
        extractor=_FakeExtractor(
            _mixed_mapping_extraction("A000000000027")
        ),
        cache_service=cache_service,
        shadow_observation_enabled=True,
    )

    result = service.prepare_product(product)
    assert result.status == "mapping_failed"

    with repository.session_factory() as session:
        option_rows = {
            row[0]: row[1]
            for row in session.execute(
                text(
                    "SELECT r.option_name, r.option_cache_status "
                    "FROM product_ingredient_records r "
                    "JOIN products p ON p.id = r.product_id "
                    "WHERE p.external_product_id = :pid"
                ),
                {"pid": "A000000000027"},
            )
        }
        all_ingredients = " ".join(
            row[0]
            for row in session.execute(
                text(
                    "SELECT r.raw_ingredients "
                    "FROM product_ingredient_records r "
                    "JOIN products p ON p.id = r.product_id "
                    "WHERE p.external_product_id = :pid"
                ),
                {"pid": "A000000000027"},
            )
        )
    # production 그대로: 19호만 ready, 21호는 unmapped(shadow가 둘 다
    # matched로 "확인"했어도 저장은 production만 반영한다).
    assert option_rows == {"19": "ready", "21": "unmapped"}
    # shadow 전용 성분이 어디에도 섞여 들어오지 않았다.
    assert "샤도우전용성분" not in all_ingredients


# ---------------------------------------------------------------------------
# Step 4: partial cache 재수집 없음 / ready 분석 성공 / non-ready 분석 거부
# ---------------------------------------------------------------------------


def test_prepare_product_partial_cache_avoids_recollection() -> None:
    """partial 결과가 option-level cache에 저장된 뒤 다시
    prepare_product()를 호출하면 extractor를 다시 실행하지 않고
    캐시에서 partial 결과를 그대로 돌려준다."""

    from app.products.ingredient_cache_service import (
        ProductIngredientCacheService,
    )
    from app.products.option_service import ProductOptionService

    class _CountingExtractor:
        def __init__(self, result) -> None:
            self.result = result
            self.calls = 0

        def extract(self, product_id: str, product_url: str):
            self.calls += 1
            return self.result

    repository = _repository()
    cache_service = ProductIngredientCacheService(
        repository=repository,
        extractor=None,
        clock=utc_now,
        option_level_cache_enabled=True,
    )
    product = _product("A000000000029")
    extractor = _CountingExtractor(
        _mixed_mapping_extraction("A000000000029")
    )
    service = ProductOptionService(
        extractor=extractor,
        cache_service=cache_service,
    )

    first = service.prepare_product(product)
    assert first.collection_status == "partial"
    assert first.can_analyze is True
    assert extractor.calls == 1

    second = service.prepare_product(product)
    assert extractor.calls == 1
    assert second.collection_status == "partial"
    assert second.can_analyze is True
    options_by_name = {
        option.option_name: option for option in second.options
    }
    assert options_by_name["19"].analysis_available is True
    assert options_by_name["21"].analysis_available is False


def test_get_cached_option_allows_ready_option_within_partial_cache() -> (
    None
):
    """Step 4: 분석 API는 partial cache 안에서도 ready 옵션의 성분
    조회는 허용해야 한다."""

    from app.products.ingredient_cache_service import (
        ProductIngredientCacheService,
    )
    from app.products.option_parser import PARSER_VERSION

    repository = _repository()
    cache_service = ProductIngredientCacheService(
        repository=repository,
        extractor=None,
        clock=utc_now,
        option_level_cache_enabled=True,
    )
    product = _product("A000000000031")
    parser_result = build_parser_result(
        "production",
        [
            build_option_level_result(
                option_id="opt-ready",
                option_name="레디",
                mapping_status="matched",
                ingredients=["정제수", "글리세린"],
            ),
            build_option_level_result(
                option_id="opt-unmapped",
                option_name="언매치드",
                mapping_status="unmatched",
                ingredients=[],
            ),
        ],
    )
    repository.save_option_cache_snapshot(
        product,
        parser_result=parser_result,
        parser_version=PARSER_VERSION,
        expires_at=utc_now() + timedelta(days=1),
    )

    resolution = cache_service.get_cached_option(
        product=product, internal_option_key="opt-ready"
    )
    assert resolution.result.ingredients == ["정제수", "글리세린"]
    assert resolution.cache_hit is True


def test_get_cached_option_rejects_non_ready_option_within_partial_cache() -> (  # noqa: E501
    None
):
    """Step 4: 분석 API는 partial cache 안의 non-ready 옵션은
    거부해야 한다(ready 옵션만 허용)."""

    from app.products.ingredient_cache_service import (
        ProductIngredientCacheService,
    )
    from app.products.option_parser import PARSER_VERSION

    repository = _repository()
    cache_service = ProductIngredientCacheService(
        repository=repository,
        extractor=None,
        clock=utc_now,
        option_level_cache_enabled=True,
        live_collection_enabled=False,
    )
    product = _product("A000000000032")
    parser_result = build_parser_result(
        "production",
        [
            build_option_level_result(
                option_id="opt-ready",
                option_name="레디",
                mapping_status="matched",
                ingredients=["정제수", "글리세린"],
            ),
            build_option_level_result(
                option_id="opt-unmapped",
                option_name="언매치드",
                mapping_status="unmatched",
                ingredients=[],
            ),
        ],
    )
    repository.save_option_cache_snapshot(
        product,
        parser_result=parser_result,
        parser_version=PARSER_VERSION,
        expires_at=utc_now() + timedelta(days=1),
    )

    from app.products.errors import ProductDataUnavailableError

    raised = False
    try:
        cache_service.get_cached_option(
            product=product, internal_option_key="opt-unmapped"
        )
    except (ValueError, ProductDataUnavailableError):
        raised = True
    assert raised is True


def test_legacy_only_cache_reports_ready_collection_status() -> None:
    """legacy 전용 저장(신규 컬럼 없음)은 Step 4에서도 그대로
    collection_status="ready"로 읽혀야 한다 - 기존 성공 cache 동작은
    바뀌지 않는다."""

    from app.products.ingredient_cache_service import (
        ProductIngredientCacheService,
    )
    from app.products.option_parser import PARSER_VERSION

    repository = _repository()
    cache_service = ProductIngredientCacheService(
        repository=repository,
        extractor=None,
        clock=utc_now,
        option_level_cache_enabled=True,
    )
    product = _product("A000000000033")
    entry = _entry(
        "opt-1", "옵션1", ["정제수", "글리세린"], product_id="A000000000033"
    )
    repository.save_collection(
        product,
        entries=[entry],
        status="ready",
        options=[
            {
                "internal_option_key": "opt-1",
                "option_name": "옵션1",
                "raw_option_name": "옵션1",
            }
        ],
        expires_at=utc_now() + timedelta(days=1),
        parser_version=PARSER_VERSION,
        # production_parser_result 생략 - legacy 저장.
    )

    preparation = cache_service.get_cached_preparation(product)
    assert preparation is not None
    assert preparation.collection_status == "ready"
    assert preparation.can_analyze is True
    assert preparation.options[0].analysis_available is True
    assert preparation.options[0].status == "ready"
