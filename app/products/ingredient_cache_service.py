from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.products.ingredient_extractors import (
    IngredientExtractor,
)
from app.products.models import (
    ProductCandidate,
    ProductIngredientResult,
)
from app.products.repositories import (
    ProductCollectionEntry,
    ProductIngredientRepository,
)
from app.products.concurrency import KeyedLockPool
from app.products.option_models import (
    ProductOption,
    ProductOptionPreparationResult,
)
from app.products.option_parser import (
    normalize_option_label,
    normalize_option_mapping_key,
)
from app.products.errors import ProductDataUnavailableError


def _option_storage_metadata(option: ProductOption) -> dict[str, object]:
    """API 비노출 원본 추적값을 포함한 DB 저장용 옵션 metadata."""

    metadata = option.model_dump(mode="json")
    metadata["source_option_names"] = list(option.source_option_names)
    metadata["source_option_ids"] = list(option.source_option_ids)
    return metadata


def utc_now() -> datetime:
    """
    현재 UTC 시간을 timezone 정보가 없는
    naive datetime으로 반환한다.

    현재 Repository와 SQLite 모델이 UTC naive datetime을
    기준으로 사용하므로 이 형식에 맞춘다.
    """

    return datetime.now(timezone.utc).replace(
        tzinfo=None
    )


@dataclass(frozen=True)
class ProductIngredientResolution:
    """
    전성분 확보 결과와 캐시 실행 정보를 함께 반환한다.

    result:
        최종 전성분 결과

    cache_hit:
        유효한 DB 캐시를 사용했는지 여부

    cache_expired:
        기존 캐시는 있었지만 만료됐는지 여부

    extraction_performed:
        이번 요청에서 실제 extractor를 실행했는지 여부
    """

    result: ProductIngredientResult
    cache_hit: bool
    cache_expired: bool
    extraction_performed: bool


class ProductIngredientCacheService:
    """
    상품 전성분 캐시 조회와 실제 추출을 조정하는 서비스.

    동작 순서:
    1. Repository에서 기존 전성분 조회
    2. 유효한 캐시가 있으면 즉시 반환
    3. 캐시가 없거나 만료됐으면 extractor 실행
    4. 추출 성공 결과만 Repository에 저장
    5. 추출 실패 결과는 저장하지 않음
    """

    def __init__(
        self,
        repository: ProductIngredientRepository,
        extractor: IngredientExtractor,
        ttl_days: int = 90,
        clock: Callable[[], datetime] | None = None,
        cache_only_mode: bool = False,
        live_collection_enabled: bool = True,
    ) -> None:
        if ttl_days <= 0:
            raise ValueError(
                "ttl_days는 1 이상이어야 합니다."
            )

        self.repository = repository
        self.extractor = extractor
        self.ttl_days = ttl_days
        self.clock = clock or utc_now
        self.cache_only_mode = cache_only_mode
        self.live_collection_enabled = live_collection_enabled
        self._extraction_locks = KeyedLockPool()

    def ensure_live_collection_allowed(self) -> None:
        if self.cache_only_mode or not self.live_collection_enabled:
            raise ProductDataUnavailableError()

    def current_time(self) -> datetime:
        return self._normalize_datetime(self.clock())

    def get_or_extract(
        self,
        product: ProductCandidate,
        option_id: str = "",
        option_name: str | None = None,
    ) -> ProductIngredientResolution:
        """
        저장된 전성분을 조회하고,
        필요할 때만 실제 추출기를 실행한다.
        """

        normalized_option_id = option_id.strip()

        # Repository의 UTC naive datetime 형식에 맞춘다.
        now = self._normalize_datetime(
            self.clock()
        )

        # 상품 출처, 외부 상품 ID, 옵션 ID를 기준으로
        # 기존 전성분 캐시를 조회한다.
        cached = (
            self.repository.get_cached_ingredients(
                source=product.source,
                external_product_id=(
                    product.product_id
                ),
                option_id=normalized_option_id,
            )
        )

        # 기존 데이터가 있는 경우에만
        # 캐시 만료 여부를 판단한다.
        cache_expired = (
            cached is not None
            and cached.is_expired(now)
        )

        # 유효한 캐시가 있으면 extractor를 실행하지 않는다.
        if (
            cached is not None
            and not cache_expired
        ):
            return ProductIngredientResolution(
                result=cached.to_result(),
                cache_hit=True,
                cache_expired=False,
                extraction_performed=False,
            )

        self.ensure_live_collection_allowed()

        collection_key = (
            f"{product.source}:{product.product_id}:{normalized_option_id}"
        )
        with self._extraction_locks.acquire(collection_key):
            # 대기 중 다른 요청이 저장했을 수 있으므로 브라우저 실행 전
            # 캐시를 다시 확인한다(single-flight double check).
            cached_after_wait = self.repository.get_cached_ingredients(
                source=product.source,
                external_product_id=product.product_id,
                option_id=normalized_option_id,
            )
            if (
                cached_after_wait is not None
                and not cached_after_wait.is_expired(now)
            ):
                return ProductIngredientResolution(
                    result=cached_after_wait.to_result(),
                    cache_hit=True,
                    cache_expired=False,
                    extraction_performed=False,
                )

            # 캐시가 없거나 만료된 경우에만 Playwright를 실행한다.
            extracted_result = self.extractor.extract(
                product_id=product.product_id,
                product_url=product.product_url,
            )

        # 추출 실패 결과는 DB에 저장하지 않는다.
        #
        # 만료된 기존 캐시가 있더라도 삭제하지 않으므로
        # 이전 데이터는 DB에 그대로 보존된다.
            if not extracted_result.extraction_success:
                return ProductIngredientResolution(
                    result=extracted_result,
                    cache_hit=False,
                    cache_expired=cache_expired,
                    extraction_performed=True,
                )

        # extraction_success가 True인데 성분 목록이 비어 있다면
        # 정상적인 추출 성공으로 볼 수 없다.
            if not extracted_result.ingredients:
                failed_result = (
                    extracted_result.model_copy(
                        update={
                            "extraction_success": False,
                            "error_message": (
                                "전성분 추출 결과가 비어 있습니다."
                            ),
                        }
                    )
                )
                return ProductIngredientResolution(
                    result=failed_result,
                    cache_hit=False,
                    cache_expired=cache_expired,
                    extraction_performed=True,
                )

        # 지금부터 TTL 기간만큼 캐시를 유효하게 설정한다.
            expires_at = now + timedelta(days=self.ttl_days)

        # 성공한 추출 결과만 Repository에 저장한다.
            self.repository.save_ingredients(
                product=product,
                result=extracted_result,
                expires_at=expires_at,
                option_id=normalized_option_id,
                option_name=option_name,
            )

            return ProductIngredientResolution(
                result=extracted_result,
                cache_hit=False,
                cache_expired=cache_expired,
                extraction_performed=True,
            )

    def get_cached_preparation(
        self,
        product: ProductCandidate,
    ) -> ProductOptionPreparationResult | None:
        getter = getattr(self.repository, "get_cached_preparation", None)
        if getter is None:
            return None
        cached = getter(
            source=product.source,
            external_product_id=product.product_id,
            now=self._normalize_datetime(self.clock()),
        )
        if cached is None:
            return None
        if cached.status == "not_applicable":
            return ProductOptionPreparationResult(
                requires_option_selection=False,
                can_analyze=True,
                status="not_applicable",
            )
        options = [
            ProductOption(
                internal_option_key=option.option_id,
                source_option_id=option.source_option_id,
                option_name=option.option_name,
                raw_option_name=option.raw_option_name or option.option_name,
                normalized_name=(
                    option.normalized_name
                    or normalize_option_label(option.option_name)
                ),
                image_url=option.image_url,
                mapping_status="matched",
                mapping_confidence=1.0,
                source_option_names=list(option.source_option_names),
                source_option_ids=list(option.source_option_ids),
            )
            for option in cached.options
        ]
        mapping_keys = [
            normalize_option_mapping_key(option.raw_option_name)
            for option in options
        ]
        # 과거 정책으로 중복 옵션이 저장된 ready cache는 새 canonical
        # 계약의 완전 HIT로 보지 않고 한 번 다시 수집한다.
        if (
            any(not key for key in mapping_keys)
            or len(mapping_keys) != len(set(mapping_keys))
        ):
            return None
        return ProductOptionPreparationResult(
            requires_option_selection=True,
            options=options,
            can_analyze=True,
            status="ready",
        )

    def mark_collection_complete(
        self,
        product: ProductCandidate,
        *,
        status: str,
        option_ids: list[str],
        options: list[ProductOption] | None = None,
        parser_version: str,
    ) -> None:
        marker = getattr(self.repository, "mark_collection_complete", None)
        if marker is None:
            return
        now = self._normalize_datetime(self.clock())
        marker(
            product,
            status=status,
            option_ids=option_ids,
            options=[
                _option_storage_metadata(option)
                for option in (options or [])
            ],
            expires_at=now + timedelta(days=self.ttl_days),
            parser_version=parser_version,
        )

    def store_collection(
        self,
        product: ProductCandidate,
        *,
        entries: list[ProductCollectionEntry],
        status: str,
        options: list[ProductOption],
        parser_version: str,
    ) -> None:
        """상품 단위 전성분과 완료 상태를 원자적으로 저장한다."""

        now = self._normalize_datetime(self.clock())
        self.repository.save_collection(
            product,
            entries=entries,
            status=status,
            options=[
                _option_storage_metadata(option)
                for option in options
            ],
            expires_at=now + timedelta(days=self.ttl_days),
            parser_version=parser_version,
        )

    def get_cached_option(
        self,
        product: ProductCandidate,
        internal_option_key: str,
    ) -> ProductIngredientResolution:
        """선택 옵션 캐시만 조회하며 전체 전성분으로 대체하지 않는다."""

        normalized_key = internal_option_key.strip()
        if not normalized_key:
            raise ValueError(
                "선택한 옵션의 internal_option_key가 비어 있습니다."
            )

        now = self._normalize_datetime(self.clock())
        cached = self.repository.get_cached_ingredients(
            source=product.source,
            external_product_id=product.product_id,
            option_id=normalized_key,
        )
        if cached is None:
            if self.cache_only_mode or not self.live_collection_enabled:
                raise ProductDataUnavailableError()
            raise ValueError(
                "선택한 옵션의 전성분 캐시가 없습니다. "
                "상품을 다시 선택해 옵션을 수집해 주세요."
            )
        if cached.is_expired(now):
            if self.cache_only_mode or not self.live_collection_enabled:
                raise ProductDataUnavailableError()
            raise ValueError(
                "선택한 옵션의 전성분 캐시가 만료되었습니다. "
                "상품을 다시 선택해 옵션을 수집해 주세요."
            )
        if not cached.ingredients:
            raise ValueError(
                "선택한 옵션의 성분 목록이 비어 있습니다."
            )

        return ProductIngredientResolution(
            result=cached.to_result(),
            cache_hit=True,
            cache_expired=False,
            extraction_performed=False,
        )

    def store_extracted(
        self,
        product: ProductCandidate,
        result: ProductIngredientResult,
        *,
        option_id: str = "",
        option_name: str | None = None,
    ) -> ProductIngredientResolution:
        """이미 분리된 기본/옵션 전성분을 기존 저장소에 저장한다."""

        if not result.extraction_success:
            raise ValueError(
                "추출에 실패한 전성분은 캐시에 저장할 수 없습니다."
            )
        if not result.ingredients:
            raise ValueError(
                "성분 목록이 비어 있는 결과는 캐시에 저장할 수 없습니다."
            )

        now = self._normalize_datetime(self.clock())
        self.repository.save_ingredients(
            product=product,
            result=result,
            expires_at=now + timedelta(days=self.ttl_days),
            option_id=option_id.strip(),
            option_name=option_name,
        )
        return ProductIngredientResolution(
            result=result,
            cache_hit=False,
            cache_expired=False,
            extraction_performed=True,
        )

    @staticmethod
    def _normalize_datetime(
        value: datetime,
    ) -> datetime:
        """
        datetime을 UTC naive 형식으로 통일한다.

        Repository의 CachedProductIngredients.is_expired()는
        SQLite에서 읽은 UTC naive datetime과 비교한다.

        timezone-aware datetime:
            UTC로 변환한 후 tzinfo 제거

        naive datetime:
            이미 UTC naive라고 보고 그대로 사용
        """

        if value.tzinfo is None:
            return value

        return value.astimezone(
            timezone.utc
        ).replace(
            tzinfo=None
        )
