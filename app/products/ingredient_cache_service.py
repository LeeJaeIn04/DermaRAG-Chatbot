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
    ProductIngredientRepository,
)


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
    ) -> None:
        if ttl_days <= 0:
            raise ValueError(
                "ttl_days는 1 이상이어야 합니다."
            )

        self.repository = repository
        self.extractor = extractor
        self.ttl_days = ttl_days
        self.clock = clock or utc_now

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

        # 캐시가 없거나 만료된 경우에만
        # Playwright 기반 extractor를 실행한다.
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
                            "전성분 추출 결과가 "
                            "비어 있습니다."
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
        expires_at = now + timedelta(
            days=self.ttl_days
        )

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
            raise ValueError(
                "선택한 옵션의 전성분 캐시가 없습니다. "
                "상품을 다시 선택해 옵션을 수집해 주세요."
            )
        if cached.is_expired(now):
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
