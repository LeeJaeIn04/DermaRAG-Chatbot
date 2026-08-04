from collections.abc import Callable, Sequence
import json
import logging
from datetime import datetime, timedelta
from hashlib import sha256

from sqlalchemy import (
    delete,
    or_,
    select,
    update,
)
from sqlalchemy.orm import (
    Session,
    joinedload,
    selectinload,
)

from app.products.db_models import (
    ProductCollectionState,
    ProductCollectionQueueRecord,
    ProductIngredientItem,
    ProductIngredientRecord,
    ProductRecord,
    ProductSearchQueryRecord,
    ProductSearchResultRecord,
    utc_now,
)
from app.products.models import (
    ProductCandidate,
    ProductIngredientResult,
)
from app.products.normalization import (
    normalize_ingredient_name,
)
from app.products.product_name_normalization import normalize_product_name
from app.products.repositories.base import (
    CachedProductOption,
    CachedProductPreparation,
    CachedProductIngredients,
    CachedProductSearch,
    ProductCollectionQueueItem,
    ProductCollectionEntry,
)
from app.products.related_models import (
    RelatedOptionMatch,
    RelatedProductMatch,
)


logger = logging.getLogger(__name__)


class SQLiteProductIngredientRepository:
    """
    SQLAlchemy Session을 사용하여 SQLite에
    상품과 전성분을 저장하고 조회한다.

    session_factory를 외부에서 받기 때문에
    실제 DB와 테스트용 임시 DB를 같은 코드로 사용할 수 있다.
    """

    def __init__(
        self,
        session_factory: Callable[[], Session],
    ) -> None:
        self.session_factory = session_factory

    def get_cached_ingredients(
        self,
        source: str,
        external_product_id: str,
        option_id: str = "",
    ) -> CachedProductIngredients | None:
        """
        source, 상품 ID, 옵션 ID로 전성분 캐시를 조회한다.
        """

        normalized_source = source.strip()
        normalized_product_id = (
            external_product_id.strip()
        )
        normalized_option_id = option_id.strip()

        with self.session_factory() as session:
            statement = (
                select(ProductIngredientRecord)
                .join(ProductIngredientRecord.product)
                .where(
                    ProductRecord.source
                    == normalized_source,
                    ProductRecord.external_product_id
                    == normalized_product_id,
                    ProductIngredientRecord.option_id
                    == normalized_option_id,
                )
                .options(
                    joinedload(
                        ProductIngredientRecord.product
                    ),
                    selectinload(
                        ProductIngredientRecord
                        .ingredient_items
                    ),
                )
            )

            record = session.scalars(
                statement
            ).first()

            if record is None:
                return None

            return self._record_to_cache(record)

    def save_ingredients(
        self,
        product: ProductCandidate,
        result: ProductIngredientResult,
        expires_at: datetime,
        option_id: str = "",
        option_name: str | None = None,
    ) -> CachedProductIngredients:
        """
        상품과 전성분을 하나의 transaction으로 저장한다.

        상품이 이미 있으면 기본 정보를 갱신한다.
        전성분이 이미 있으면 원문과 개별 성분을 교체한다.
        """

        if not result.extraction_success:
            raise ValueError(
                "추출에 실패한 전성분은 저장할 수 없습니다."
            )

        if not result.raw_ingredients.strip():
            raise ValueError(
                "전성분 원문이 비어 있습니다."
            )

        if not result.ingredients:
            raise ValueError(
                "저장할 개별 성분 목록이 비어 있습니다."
            )

        if (
            result.product_id.strip()
            != product.product_id.strip()
        ):
            raise ValueError(
                "상품 ID와 추출 결과의 상품 ID가 "
                "일치하지 않습니다."
            )

        normalized_option_id = option_id.strip()

        # hash는 전성분 원문의 앞뒤 공백을 제거한 값을
        # 기준으로 생성한다.
        raw_ingredients = (
            result.raw_ingredients.strip()
        )

        ingredient_hash = sha256(
            raw_ingredients.encode("utf-8")
        ).hexdigest()

        now = utc_now()

        with self.session_factory() as session:
            try:
                product_record = (
                    self._get_or_create_product(
                        session=session,
                        product=product,
                    )
                )

                ingredient_record = (
                    self._get_ingredient_record(
                        session=session,
                        product_id=product_record.id,
                        option_id=normalized_option_id,
                    )
                )

                if ingredient_record is None:
                    ingredient_record = (
                        ProductIngredientRecord(
                            product=product_record,
                            option_id=(
                                normalized_option_id
                            ),
                            option_name=option_name,
                            raw_ingredients=(
                                raw_ingredients
                            ),
                            ingredient_hash=(
                                ingredient_hash
                            ),
                            extraction_method=(
                                result.extraction_method
                            ),
                            extracted_at=now,
                            last_checked_at=now,
                            expires_at=expires_at,
                        )
                    )

                    session.add(ingredient_record)
                    session.flush()

                else:
                    # 기존 전성분 캐시를 최신 결과로 갱신한다.
                    ingredient_record.option_name = (
                        option_name
                    )
                    ingredient_record.raw_ingredients = (
                        raw_ingredients
                    )
                    ingredient_record.ingredient_hash = (
                        ingredient_hash
                    )
                    ingredient_record.extraction_method = (
                        result.extraction_method
                    )
                    ingredient_record.extracted_at = now
                    ingredient_record.last_checked_at = now
                    ingredient_record.expires_at = (
                        expires_at
                    )

                    # 기존 개별 성분을 먼저 삭제한다.
                    #
                    # 동일한 position을 바로 다시 추가하면
                    # unique constraint와 충돌할 수 있으므로
                    # 삭제 후 flush한다.
                    session.execute(
                        delete(ProductIngredientItem)
                        .where(
                            ProductIngredientItem
                            .ingredient_record_id
                            == ingredient_record.id
                        )
                    )
                    session.flush()

                # 새 성분 목록을 순서대로 저장한다.
                for position, ingredient_name in enumerate(
                    result.ingredients,
                    start=1,
                ):
                    cleaned_name = ingredient_name.strip()

                    if not cleaned_name:
                        continue

                    session.add(
                        ProductIngredientItem(
                            ingredient_record_id=(
                                ingredient_record.id
                            ),
                            ingredient_name=cleaned_name,
                            normalized_name=(
                                normalize_ingredient_name(
                                    cleaned_name
                                )
                            ),
                            position=position,
                        )
                    )

                session.commit()

                # commit 후 관계 데이터를 다시 조회해
                # 완전한 캐시 모델로 변환한다.
                saved_record = (
                    self._get_ingredient_record_with_items(
                        session=session,
                        record_id=ingredient_record.id,
                    )
                )

                if saved_record is None:
                    raise RuntimeError(
                        "저장한 전성분을 다시 조회하지 "
                        "못했습니다."
                    )

                return self._record_to_cache(
                    saved_record
                )

            except Exception:
                session.rollback()
                raise

    def get_cached_preparation(
        self,
        source: str,
        external_product_id: str,
        now: datetime,
    ) -> CachedProductPreparation | None:
        """완료 표시와 실제 캐시 레코드가 모두 일치할 때만 HIT 처리한다."""

        with self.session_factory() as session:
            product = session.scalars(
                select(ProductRecord)
                .where(
                    ProductRecord.source == source.strip(),
                    ProductRecord.external_product_id
                    == external_product_id.strip(),
                )
                .options(
                    joinedload(ProductRecord.collection_state),
                    selectinload(ProductRecord.ingredient_records).selectinload(
                        ProductIngredientRecord.ingredient_items
                    ),
                )
            ).first()
            if product is None or product.collection_state is None:
                return None

            state = product.collection_state
            if state.expires_at <= now:
                return None

            records = [
                record
                for record in product.ingredient_records
                if record.expires_at > now and record.ingredient_items
            ]
            if state.status == "not_applicable":
                if state.option_count != 0 or not any(
                    record.option_id == "" for record in records
                ):
                    return None
                return CachedProductPreparation(status="not_applicable")

            option_records = [record for record in records if record.option_id]
            if state.status != "ready" or len(option_records) != state.option_count:
                return None

            try:
                metadata_by_id = {
                    str(item["internal_option_key"]): item
                    for item in json.loads(state.options_json)
                    if isinstance(item, dict) and item.get("internal_option_key")
                }
            except (TypeError, ValueError, json.JSONDecodeError):
                metadata_by_id = {}
            options = tuple(
                CachedProductOption(
                    option_id=record.option_id,
                    option_name=record.option_name or record.option_id,
                    source_option_id=metadata_by_id.get(record.option_id, {}).get(
                        "source_option_id"
                    ),
                    raw_option_name=metadata_by_id.get(record.option_id, {}).get(
                        "raw_option_name"
                    ),
                    normalized_name=metadata_by_id.get(record.option_id, {}).get(
                        "normalized_name"
                    ),
                    image_url=metadata_by_id.get(record.option_id, {}).get(
                        "image_url"
                    ),
                    source_option_names=tuple(
                        metadata_by_id.get(record.option_id, {}).get(
                            "source_option_names", []
                        )
                    ),
                    source_option_ids=tuple(
                        metadata_by_id.get(record.option_id, {}).get(
                            "source_option_ids", []
                        )
                    ),
                )
                for record in sorted(option_records, key=lambda item: item.option_id)
            )
            return CachedProductPreparation(status="ready", options=options)

    def mark_collection_complete(
        self,
        product: ProductCandidate,
        *,
        status: str,
        option_ids: list[str],
        options: list[dict[str, object]],
        expires_at: datetime,
        parser_version: str,
    ) -> None:
        """부분 저장을 HIT로 보지 않도록 마지막 transaction에서 상태를 확정한다."""

        normalized_ids = {value.strip() for value in option_ids}
        with self.session_factory() as session:
            try:
                product_record = self._get_or_create_product(session, product)
                session.execute(
                    delete(ProductIngredientRecord).where(
                        ProductIngredientRecord.product_id == product_record.id,
                        ProductIngredientRecord.option_id.not_in(normalized_ids),
                    )
                )
                state = session.scalars(
                    select(ProductCollectionState).where(
                        ProductCollectionState.product_id == product_record.id
                    )
                ).first()
                if state is None:
                    state = ProductCollectionState(
                        product=product_record,
                        status=status,
                        option_count=len([value for value in normalized_ids if value]),
                        parser_version=parser_version,
                        options_json=json.dumps(options, ensure_ascii=False),
                        expires_at=expires_at,
                    )
                    session.add(state)
                else:
                    state.status = status
                    state.option_count = len(
                        [value for value in normalized_ids if value]
                    )
                    state.parser_version = parser_version
                    state.options_json = json.dumps(options, ensure_ascii=False)
                    state.collected_at = utc_now()
                    state.expires_at = expires_at
                session.commit()
            except Exception:
                session.rollback()
                raise

    def save_collection(
        self,
        product: ProductCandidate,
        *,
        entries: Sequence[ProductCollectionEntry],
        status: str,
        options: list[dict[str, object]],
        expires_at: datetime,
        parser_version: str,
    ) -> None:
        """전성분 레코드 전체와 완료 상태를 원자적으로 교체한다."""

        if status not in {"ready", "not_applicable"} or not entries:
            raise ValueError("완료 상태와 전성분 항목이 올바르지 않습니다.")
        normalized_ids = [entry.option_id.strip() for entry in entries]
        if len(normalized_ids) != len(set(normalized_ids)):
            raise ValueError("중복된 옵션 ID는 저장할 수 없습니다.")
        if status == "not_applicable" and normalized_ids != [""]:
            raise ValueError("옵션 없는 상품은 공통 전성분 하나만 필요합니다.")
        if status == "ready" and any(not value for value in normalized_ids):
            raise ValueError("옵션 상품의 option_id는 비어 있을 수 없습니다.")

        with self.session_factory() as session:
            try:
                product_record = self._get_or_create_product(session, product)
                for entry in entries:
                    self._upsert_collection_entry(
                        session,
                        product_record=product_record,
                        entry=entry,
                        expires_at=expires_at,
                    )

                session.execute(
                    delete(ProductIngredientRecord).where(
                        ProductIngredientRecord.product_id == product_record.id,
                        ProductIngredientRecord.option_id.not_in(set(normalized_ids)),
                    )
                )
                state = session.scalars(
                    select(ProductCollectionState).where(
                        ProductCollectionState.product_id == product_record.id
                    )
                ).first()
                if state is None:
                    state = ProductCollectionState(product=product_record)
                    session.add(state)
                state.status = status
                state.option_count = len([value for value in normalized_ids if value])
                state.parser_version = parser_version
                state.options_json = json.dumps(options, ensure_ascii=False)
                state.collected_at = utc_now()
                state.expires_at = expires_at
                queue = session.scalars(
                    select(ProductCollectionQueueRecord).where(
                        ProductCollectionQueueRecord.product_id
                        == product_record.id
                    )
                ).first()
                if queue is None:
                    queue = ProductCollectionQueueRecord(
                        product=product_record,
                        status="complete",
                    )
                    session.add(queue)
                else:
                    queue.status = "complete"
                    queue.next_retry_at = None
                    queue.updated_at = utc_now()
                session.commit()
            except Exception:
                session.rollback()
                raise

    @staticmethod
    def _upsert_collection_entry(
        session: Session,
        *,
        product_record: ProductRecord,
        entry: ProductCollectionEntry,
        expires_at: datetime,
    ) -> None:
        result = entry.result
        if (
            not result.extraction_success
            or not result.raw_ingredients.strip()
            or not result.ingredients
        ):
            raise ValueError("완전하지 않은 전성분 결과는 저장할 수 없습니다.")
        if result.product_id.strip() != product_record.external_product_id:
            raise ValueError("상품 ID와 전성분 결과가 일치하지 않습니다.")

        option_id = entry.option_id.strip()
        raw_ingredients = result.raw_ingredients.strip()
        now = utc_now()
        record = session.scalars(
            select(ProductIngredientRecord).where(
                ProductIngredientRecord.product_id == product_record.id,
                ProductIngredientRecord.option_id == option_id,
            )
        ).first()
        if record is None:
            record = ProductIngredientRecord(
                product=product_record,
                option_id=option_id,
                option_name=entry.option_name,
                raw_ingredients=raw_ingredients,
                ingredient_hash=sha256(
                    raw_ingredients.encode("utf-8")
                ).hexdigest(),
                extraction_method=result.extraction_method,
                extracted_at=now,
                last_checked_at=now,
                expires_at=expires_at,
            )
            session.add(record)
            session.flush()
        else:
            record.option_name = entry.option_name
            record.raw_ingredients = raw_ingredients
            record.ingredient_hash = sha256(
                raw_ingredients.encode("utf-8")
            ).hexdigest()
            record.extraction_method = result.extraction_method
            record.extracted_at = now
            record.last_checked_at = now
            record.expires_at = expires_at
            session.execute(
                delete(ProductIngredientItem).where(
                    ProductIngredientItem.ingredient_record_id == record.id
                )
            )
            session.flush()

        for position, ingredient_name in enumerate(result.ingredients, start=1):
            cleaned_name = ingredient_name.strip()
            if not cleaned_name:
                continue
            session.add(
                ProductIngredientItem(
                    ingredient_record_id=record.id,
                    ingredient_name=cleaned_name,
                    normalized_name=normalize_ingredient_name(cleaned_name),
                    position=position,
                )
            )

    def find_products_by_ingredient(
        self,
        ingredient_name: str,
        limit: int = 10,
    ) -> list[ProductCandidate]:
        """
        정규화된 성분명이 정확히 일치하는 상품을 조회한다.

        같은 상품의 여러 옵션에 동일한 성분이 있어도
        상품은 중복 없이 반환한다.
        """

        normalized_name = normalize_ingredient_name(
            ingredient_name
        )

        if not normalized_name:
            return []

        if limit <= 0:
            return []

        with self.session_factory() as session:
            statement = (
                select(ProductRecord)
                .join(
                    ProductRecord.ingredient_records
                )
                .join(
                    ProductIngredientRecord
                    .ingredient_items
                )
                .where(
                    ProductIngredientItem.normalized_name
                    == normalized_name
                )
                .distinct()
                .limit(limit)
            )

            product_records = list(
                session.scalars(statement).all()
            )

            return [
                self._product_record_to_candidate(
                    product_record
                )
                for product_record in product_records
            ]

    def get_product_candidate(
        self,
        source: str,
        external_product_id: str,
    ) -> ProductCandidate | None:
        with self.session_factory() as session:
            record = session.scalars(
                select(ProductRecord).where(
                    ProductRecord.source == source.strip(),
                    ProductRecord.external_product_id
                    == external_product_id.strip(),
                )
            ).first()
            return (
                self._product_record_to_candidate(record)
                if record is not None
                else None
            )

    def get_cached_search(
        self,
        normalized_query: str,
        *,
        now: datetime,
    ) -> CachedProductSearch | None:
        with self.session_factory() as session:
            query_record = session.scalars(
                select(ProductSearchQueryRecord)
                .where(
                    ProductSearchQueryRecord.normalized_query
                    == normalized_query.strip()
                )
                .options(
                    selectinload(ProductSearchQueryRecord.results).joinedload(
                        ProductSearchResultRecord.product
                    )
                )
            ).first()
            if query_record is None or query_record.expires_at <= now:
                return None
            products = tuple(
                self._product_record_to_candidate(result.product).model_copy(
                    update={
                        "rank": result.rank,
                        "search_query": normalized_query,
                        "fetched_at": query_record.searched_at,
                    }
                )
                for result in sorted(query_record.results, key=lambda item: item.rank)
            )
            return CachedProductSearch(
                products=products,
                searched_at=query_record.searched_at,
                expires_at=query_record.expires_at,
            )

    def save_search_results(
        self,
        normalized_query: str,
        products: Sequence[ProductCandidate],
        *,
        searched_at: datetime,
        expires_at: datetime,
    ) -> CachedProductSearch:
        query_value = normalized_query.strip()
        if not query_value:
            raise ValueError("정규화 검색어가 비어 있습니다.")
        with self.session_factory() as session:
            try:
                query_record = session.scalars(
                    select(ProductSearchQueryRecord).where(
                        ProductSearchQueryRecord.normalized_query == query_value
                    )
                ).first()
                if query_record is None:
                    query_record = ProductSearchQueryRecord(
                        normalized_query=query_value,
                        searched_at=searched_at,
                        expires_at=expires_at,
                    )
                    session.add(query_record)
                    session.flush()
                else:
                    query_record.searched_at = searched_at
                    query_record.expires_at = expires_at
                    session.execute(
                        delete(ProductSearchResultRecord).where(
                            ProductSearchResultRecord.query_id == query_record.id
                        )
                    )
                    session.flush()

                saved_products: list[ProductCandidate] = []
                seen: set[tuple[str, str]] = set()
                for fallback_rank, product in enumerate(products, start=1):
                    identity = (product.source.strip(), product.product_id.strip())
                    if identity in seen:
                        continue
                    seen.add(identity)
                    product_record = self._get_or_create_product(session, product)
                    rank = fallback_rank
                    session.add(
                        ProductSearchResultRecord(
                            query=query_record,
                            product=product_record,
                            rank=rank,
                        )
                    )
                    queue = session.scalars(
                        select(ProductCollectionQueueRecord).where(
                            ProductCollectionQueueRecord.product_id
                            == product_record.id
                        )
                    ).first()
                    if queue is None:
                        queue = ProductCollectionQueueRecord(
                            product=product_record,
                            status=(
                                "complete"
                                if product_record.collection_state is not None
                                and product_record.collection_state.expires_at
                                > searched_at
                                else "pending"
                            ),
                        )
                        session.add(queue)
                    saved_products.append(
                        product.model_copy(
                            update={
                                "rank": rank,
                                "search_query": query_value,
                                "fetched_at": searched_at,
                            }
                        )
                    )
                session.commit()
                return CachedProductSearch(
                    products=tuple(saved_products),
                    searched_at=searched_at,
                    expires_at=expires_at,
                )
            except Exception:
                session.rollback()
                raise

    def start_collection_attempt(
        self,
        product: ProductCandidate,
        *,
        now: datetime,
        force: bool = False,
        collecting_lease_timeout_seconds: int = 90,
    ) -> ProductCollectionQueueItem:
        if collecting_lease_timeout_seconds <= 0:
            raise ValueError(
                "collecting lease timeout은 1초 이상이어야 합니다."
            )
        with self.session_factory() as session:
            try:
                product_record = self._get_or_create_product(session, product)
                queue = session.scalars(
                    select(ProductCollectionQueueRecord).where(
                        ProductCollectionQueueRecord.product_id == product_record.id
                    )
                ).first()
                if queue is None:
                    queue = ProductCollectionQueueRecord(
                        product=product_record, status="pending"
                    )
                    session.add(queue)
                    session.flush()
                stale_before = now - timedelta(
                    seconds=collecting_lease_timeout_seconds
                )
                stale_collecting = (
                    queue.status == "collecting"
                    and queue.last_attempt_at is not None
                    and queue.last_attempt_at < stale_before
                )
                previous_attempt_count = queue.attempt_count
                claimable = or_(
                    ProductCollectionQueueRecord.status.not_in(
                        ("collecting", "failed")
                    ),
                    (
                        (ProductCollectionQueueRecord.status == "failed")
                        & (
                            ProductCollectionQueueRecord.next_retry_at.is_(None)
                            | (ProductCollectionQueueRecord.next_retry_at <= now)
                        )
                    ),
                    (
                        (ProductCollectionQueueRecord.status == "collecting")
                        & ProductCollectionQueueRecord.last_attempt_at.is_not(None)
                        & (
                            ProductCollectionQueueRecord.last_attempt_at
                            < stale_before
                        )
                    ),
                )
                statement = (
                    update(ProductCollectionQueueRecord)
                    .where(
                        ProductCollectionQueueRecord.product_id
                        == product_record.id
                    )
                    .values(
                        status="collecting",
                        attempt_count=(
                            ProductCollectionQueueRecord.attempt_count + 1
                        ),
                        last_attempt_at=now,
                        next_retry_at=None,
                        updated_at=now,
                    )
                )
                if not force:
                    statement = statement.where(claimable)
                claimed = session.execute(
                    statement.execution_options(synchronize_session=False)
                )
                if claimed.rowcount != 1:
                    session.rollback()
                    current_product = session.scalars(
                        select(ProductRecord).where(
                            ProductRecord.id == product_record.id
                        )
                    ).one()
                    current_queue = session.scalars(
                        select(ProductCollectionQueueRecord).where(
                            ProductCollectionQueueRecord.product_id
                            == current_product.id
                        )
                    ).one()
                    return self._queue_to_item(
                        current_queue,
                        current_product,
                        attempt_started=False,
                    )
                session.commit()
                session.expire_all()
                current_queue = session.scalars(
                    select(ProductCollectionQueueRecord).where(
                        ProductCollectionQueueRecord.product_id
                        == product_record.id
                    )
                ).one()
                if stale_collecting:
                    logger.warning(
                        "Recovered stale product collection lease "
                        "(source=%s, product_id=%s, previous_attempt=%d, "
                        "lease_timeout_seconds=%d)",
                        product.source,
                        product.product_id,
                        previous_attempt_count,
                        collecting_lease_timeout_seconds,
                    )
                return self._queue_to_item(
                    current_queue,
                    product_record,
                    attempt_started=True,
                )
            except Exception:
                session.rollback()
                raise

    def finish_collection_attempt(
        self,
        product: ProductCandidate,
        *,
        success: bool,
        now: datetime,
        retry_base_seconds: int,
        retry_max_seconds: int,
    ) -> ProductCollectionQueueItem:
        with self.session_factory() as session:
            try:
                product_record = self._get_or_create_product(session, product)
                queue = session.scalars(
                    select(ProductCollectionQueueRecord).where(
                        ProductCollectionQueueRecord.product_id == product_record.id
                    )
                ).first()
                if queue is None:
                    queue = ProductCollectionQueueRecord(
                        product=product_record,
                        status="collecting",
                        attempt_count=0 if success else 1,
                        last_attempt_at=None if success else now,
                    )
                    session.add(queue)
                    session.flush()
                queue.status = "complete" if success else "failed"
                queue.updated_at = now
                if success:
                    queue.next_retry_at = None
                else:
                    exponent = min(max(queue.attempt_count - 1, 0), 20)
                    delay = min(
                        retry_max_seconds,
                        retry_base_seconds * (2**exponent),
                    )
                    queue.next_retry_at = now + timedelta(seconds=delay)
                session.commit()
                return self._queue_to_item(queue, product_record)
            except Exception:
                session.rollback()
                raise

    def list_collection_queue(
        self,
        *,
        now: datetime,
        limit: int,
        collecting_lease_timeout_seconds: int = 90,
    ) -> list[ProductCollectionQueueItem]:
        if limit <= 0:
            return []
        if collecting_lease_timeout_seconds <= 0:
            raise ValueError(
                "collecting lease timeout은 1초 이상이어야 합니다."
            )
        stale_before = now - timedelta(
            seconds=collecting_lease_timeout_seconds
        )
        with self.session_factory() as session:
            records = session.scalars(
                select(ProductCollectionQueueRecord)
                .join(ProductCollectionQueueRecord.product)
                .where(
                    (ProductCollectionQueueRecord.status == "pending")
                    | (
                        (ProductCollectionQueueRecord.status == "failed")
                        & (
                            (ProductCollectionQueueRecord.next_retry_at.is_(None))
                            | (ProductCollectionQueueRecord.next_retry_at <= now)
                        )
                    )
                    | (
                        (ProductCollectionQueueRecord.status == "collecting")
                        & ProductCollectionQueueRecord.last_attempt_at.is_not(None)
                        & (
                            ProductCollectionQueueRecord.last_attempt_at
                            < stale_before
                        )
                    )
                )
                .options(joinedload(ProductCollectionQueueRecord.product))
                .order_by(
                    ProductCollectionQueueRecord.updated_at,
                    ProductCollectionQueueRecord.id,
                )
                .limit(limit)
            ).all()
            return [self._queue_to_item(record, record.product) for record in records]

    @classmethod
    def _queue_to_item(
        cls,
        queue: ProductCollectionQueueRecord,
        product: ProductRecord,
        attempt_started: bool = False,
    ) -> ProductCollectionQueueItem:
        return ProductCollectionQueueItem(
            product=cls._product_record_to_candidate(product),
            status=queue.status,
            attempt_count=queue.attempt_count,
            last_attempt_at=queue.last_attempt_at,
            next_retry_at=queue.next_retry_at,
            attempt_started=attempt_started,
        )

    def search_complete_products(
        self,
        query: str,
        *,
        now: datetime,
        limit: int = 5,
    ) -> list[ProductCandidate]:
        normalized_query = normalize_product_name(query)
        if not normalized_query or limit <= 0:
            return []
        with self.session_factory() as session:
            records = list(session.scalars(
                select(ProductRecord)
                .join(ProductRecord.collection_state)
                .where(
                    ProductCollectionState.expires_at > now,
                    ProductCollectionState.status.in_(
                        ("ready", "not_applicable")
                    ),
                    (
                        ProductRecord.normalized_product_name.contains(
                            normalized_query
                        )
                        | ProductRecord.brand_name.contains(normalized_query)
                    ),
                )
                .options(
                    joinedload(ProductRecord.collection_state),
                    selectinload(ProductRecord.ingredient_records).selectinload(
                        ProductIngredientRecord.ingredient_items
                    ),
                )
                .order_by(ProductRecord.updated_at.desc(), ProductRecord.id)
            ).unique().all())
            complete = [
                record
                for record in records
                if self._valid_complete_records(
                    record, now=now, include_legacy=False
                )
                is not None
            ]
            return [
                self._product_record_to_candidate(record)
                for record in complete[:limit]
            ]

    def search_products_by_text(
        self,
        query: str,
        *,
        now: datetime,
        limit: int = 10,
    ) -> list[ProductCandidate]:
        query_value = query.strip()
        normalized_query = normalize_product_name(query)
        if not normalized_query or limit <= 0:
            return []
        with self.session_factory() as session:
            records = session.scalars(
                select(ProductRecord)
                .outerjoin(ProductRecord.search_results)
                .outerjoin(ProductSearchResultRecord.query)
                .outerjoin(ProductRecord.collection_state)
                .where(
                    (
                        (ProductSearchQueryRecord.expires_at > now)
                        | (
                            (ProductCollectionState.expires_at > now)
                            & ProductCollectionState.status.in_(
                                ("ready", "not_applicable")
                            )
                        )
                    ),
                    (
                        ProductRecord.normalized_product_name.contains(
                            normalized_query
                        )
                        | ProductRecord.brand_name.contains(query_value)
                    ),
                )
                .distinct()
                .order_by(ProductRecord.updated_at.desc(), ProductRecord.id)
                .limit(limit)
            ).all()
            return [self._product_record_to_candidate(record) for record in records]

    def find_related_products_by_ingredients(
        self,
        normalized_ingredient_names: Sequence[str],
        *,
        exclude_product_id: int | None = None,
        exclude_source: str | None = None,
        exclude_external_product_id: str | None = None,
        category: str | None = None,
        category_path: str | None = None,
        limit: int = 5,
        include_legacy: bool = False,
    ) -> list[RelatedProductMatch]:
        names = tuple(dict.fromkeys(name.strip() for name in normalized_ingredient_names if name.strip()))
        if not names or limit <= 0:
            return []
        now = utc_now()

        with self.session_factory() as session:
            statement = (
                select(ProductRecord)
                .join(ProductRecord.ingredient_records)
                .join(ProductIngredientRecord.ingredient_items)
                .where(ProductIngredientItem.normalized_name.in_(names))
                .options(
                    joinedload(ProductRecord.collection_state),
                    selectinload(ProductRecord.ingredient_records).selectinload(
                        ProductIngredientRecord.ingredient_items
                    ),
                )
                .distinct()
            )
            if exclude_product_id is not None:
                statement = statement.where(ProductRecord.id != exclude_product_id)
            if exclude_source and exclude_external_product_id:
                statement = statement.where(
                    ~(
                        (ProductRecord.source == exclude_source.strip())
                        & (
                            ProductRecord.external_product_id
                            == exclude_external_product_id.strip()
                        )
                    )
                )
            products = list(session.scalars(statement).unique().all())

            matches: list[tuple[tuple[object, ...], RelatedProductMatch]] = []
            name_set = set(names)
            for product in products:
                records = self._valid_complete_records(
                    product, now=now, include_legacy=include_legacy
                )
                if records is None:
                    continue

                option_matches: list[RelatedOptionMatch] = []
                product_names: dict[str, str] = {}
                for record in records:
                    record_names: dict[str, str] = {}
                    for item in record.ingredient_items:
                        if item.normalized_name in name_set:
                            record_names.setdefault(
                                item.normalized_name, item.ingredient_name
                            )
                            product_names.setdefault(
                                item.normalized_name, item.ingredient_name
                            )
                    if record.option_id and record_names:
                        option_matches.append(
                            RelatedOptionMatch(
                                option_id=record.option_id,
                                option_name=record.option_name,
                                matched_ingredients=[
                                    record_names[name]
                                    for name in names
                                    if name in record_names
                                ],
                            )
                        )
                if not product_names:
                    continue

                match_level = self._category_match_level(
                    product.category,
                    product.category_path,
                    category,
                    category_path,
                )
                result = RelatedProductMatch(
                    product_id=product.id,
                    source=product.source,
                    external_product_id=product.external_product_id,
                    product_name=product.product_name,
                    brand_name=product.brand_name,
                    category=product.category,
                    category_path=product.category_path,
                    product_url=product.product_url,
                    image_url=product.image_url,
                    matched_ingredients=[
                        product_names[name] for name in names if name in product_names
                    ],
                    matched_options=sorted(
                        option_matches, key=lambda option: option.option_id
                    ),
                    category_match_level=match_level,
                )
                rank = {
                    "same_category": 0,
                    "same_parent_path": 1,
                    "other_category": 2,
                }[match_level]
                matches.append(
                    (
                        (
                            rank,
                            -len(result.matched_ingredients),
                            -len(result.matched_options),
                            -product.updated_at.timestamp(),
                            product.source,
                            product.external_product_id,
                        ),
                        result,
                    )
                )

            matches.sort(key=lambda item: item[0])
            return [result for _, result in matches[:limit]]

    @staticmethod
    def _valid_complete_records(
        product: ProductRecord,
        *,
        now: datetime,
        include_legacy: bool,
    ) -> list[ProductIngredientRecord] | None:
        valid = [
            record
            for record in product.ingredient_records
            if record.expires_at > now and record.ingredient_items
        ]
        state = product.collection_state
        if state is None:
            return (valid or None) if include_legacy else None
        if state.expires_at <= now:
            return None
        if state.status == "not_applicable":
            common = [record for record in valid if record.option_id == ""]
            return common if state.option_count == 0 and len(common) == 1 else None
        options = [record for record in valid if record.option_id]
        if state.status != "ready" or len(options) != state.option_count:
            return None
        return options

    @staticmethod
    def _category_match_level(
        candidate_category: str | None,
        candidate_path: str | None,
        category: str | None,
        category_path: str | None,
    ) -> str:
        if category and candidate_category == category:
            return "same_category"

        def parent(value: str | None) -> tuple[str, ...]:
            parts = tuple(
                part.strip() for part in (value or "").split(">") if part.strip()
            )
            return parts[:-1] if len(parts) > 1 else ()

        requested_parent = parent(category_path)
        if requested_parent and parent(candidate_path) == requested_parent:
            return "same_parent_path"
        return "other_category"

    @staticmethod
    def _get_or_create_product(
        session: Session,
        product: ProductCandidate,
    ) -> ProductRecord:
        """
        기존 상품을 조회하거나 새 상품을 생성한다.

        기존 상품인 경우 최신 이름, URL, category로 갱신한다.
        """

        statement = select(ProductRecord).where(
            ProductRecord.source
            == product.source.strip(),
            ProductRecord.external_product_id
            == product.product_id.strip(),
        )

        product_record = session.scalars(
            statement
        ).first()

        if product_record is None:
            product_record = ProductRecord(
                source=product.source.strip(),
                external_product_id=(
                    product.product_id.strip()
                ),
                brand_name=product.brand_name,
                product_name=product.product_name,
                normalized_product_name=normalize_product_name(
                    product.product_name
                ),
                category=product.category,
                category_path=product.category_path,
                product_url=product.product_url,
                image_url=product.image_url,
            )

            session.add(product_record)
            session.flush()

            return product_record

        # 이미 저장된 상품은 검색 결과의 최신 정보로 갱신한다.
        product_record.brand_name = product.brand_name
        product_record.product_name = (
            product.product_name
        )
        product_record.normalized_product_name = normalize_product_name(
            product.product_name
        )
        product_record.category = product.category
        product_record.category_path = (
            product.category_path
        )
        product_record.product_url = product.product_url
        product_record.image_url = product.image_url
        product_record.updated_at = utc_now()

        session.flush()

        return product_record

    @staticmethod
    def _get_ingredient_record(
        session: Session,
        product_id: int,
        option_id: str,
    ) -> ProductIngredientRecord | None:
        """
        상품 DB ID와 옵션 ID로 전성분 레코드를 조회한다.
        """

        statement = (
            select(ProductIngredientRecord)
            .where(
                ProductIngredientRecord.product_id
                == product_id,
                ProductIngredientRecord.option_id
                == option_id,
            )
        )

        return session.scalars(statement).first()

    @staticmethod
    def _get_ingredient_record_with_items(
        session: Session,
        record_id: int,
    ) -> ProductIngredientRecord | None:
        """
        상품, 개별 성분 관계를 함께 조회한다.
        """

        statement = (
            select(ProductIngredientRecord)
            .where(
                ProductIngredientRecord.id
                == record_id
            )
            .options(
                joinedload(
                    ProductIngredientRecord.product
                ),
                selectinload(
                    ProductIngredientRecord
                    .ingredient_items
                ),
            )
        )

        return session.scalars(statement).first()

    @staticmethod
    def _record_to_cache(
        record: ProductIngredientRecord,
    ) -> CachedProductIngredients:
        """
        SQLAlchemy ORM 객체를 Repository 반환 모델로 변환한다.
        """

        sorted_items = sorted(
            record.ingredient_items,
            key=lambda item: item.position,
        )

        return CachedProductIngredients(
            product_id=(
                record.product.external_product_id
            ),
            source=record.product.source,
            product_url=record.product.product_url,
            raw_ingredients=record.raw_ingredients,
            ingredients=tuple(
                item.ingredient_name
                for item in sorted_items
            ),
            extraction_method=(
                record.extraction_method
            ),
            ingredient_hash=record.ingredient_hash,
            extracted_at=record.extracted_at,
            last_checked_at=record.last_checked_at,
            expires_at=record.expires_at,
            option_id=record.option_id,
            option_name=record.option_name,
        )

    @staticmethod
    def _product_record_to_candidate(
        record: ProductRecord,
    ) -> ProductCandidate:
        """
        DB 상품 객체를 API에서 사용하는 상품 후보로 변환한다.
        """

        return ProductCandidate(
            product_id=record.external_product_id,
            source=record.source,
            brand_name=record.brand_name,
            product_name=record.product_name,
            category=record.category,
            category_path=record.category_path,
            product_url=record.product_url,
            image_url=record.image_url,
        )
