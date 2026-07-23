from collections.abc import Callable
from datetime import datetime
from hashlib import sha256

from sqlalchemy import (
    delete,
    select,
)
from sqlalchemy.orm import (
    Session,
    joinedload,
    selectinload,
)

from app.products.db_models import (
    ProductIngredientItem,
    ProductIngredientRecord,
    ProductRecord,
    utc_now,
)
from app.products.models import (
    ProductCandidate,
    ProductIngredientResult,
)
from app.products.normalization import (
    normalize_ingredient_name,
)
from app.products.repositories.base import (
    CachedProductIngredients,
)


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