from __future__ import annotations
from app.allergens.schemas import (
    FragranceAllergenMatch,
)
from app.products.schemas import (
    ProductFragranceAllergenSource,
)


def build_product_allergens(
    matches: list[FragranceAllergenMatch],
) -> list[ProductFragranceAllergenSource]:
    """
    식약처 향료 알레르겐 Repository의
    내부 exact match 모델을 상품 분석 API
    응답 모델로 변환한다.
    """

    results: list[
        ProductFragranceAllergenSource
    ] = []

    for match in matches:
        allergen = match.allergen

        results.append(
            ProductFragranceAllergenSource(
                query_ingredient=(
                    match.query_ingredient
                ),
                matched_name=(
                    match.matched_name
                ),
                match_type=match.match_type,
                ingredient_kor_name=(
                    allergen.ingredient_kor_name
                ),
                ingredient_eng_name=(
                    allergen.ingredient_eng_name
                ),
                inci_name=allergen.inci_name,
                cas_numbers=(
                    allergen.cas_numbers
                ),
                aliases=allergen.aliases,
                allergen_type=(
                    allergen.allergen_type
                ),
                legal_status=(
                    allergen.legal_status
                ),
                jurisdiction=(
                    allergen.jurisdiction
                ),
                evidence_scope=(
                    allergen.evidence_scope
                ),
                rinse_off_threshold=(
                    allergen.rinse_off_threshold
                ),
                leave_on_threshold=(
                    allergen.leave_on_threshold
                ),
                source_id=allergen.source_id,
                source_authority=(
                    allergen.source_authority
                ),
                source_document=(
                    allergen.source_document
                ),
                source_document_version=(
                    allergen
                    .source_document_version
                ),
                source_document_date=(
                    allergen
                    .source_document_date
                ),
                source_section=(
                    allergen.source_section
                ),
                source_page=(
                    allergen.source_page
                ),
                source_row=(
                    allergen.source_row
                ),
            )
        )

    return results

def build_allergen_context(
    allergens: list[
        ProductFragranceAllergenSource
    ],
) -> str:
    """
    식약처 향료 알레르기 표시 대상 정보를
    Gemini 프롬프트에 전달할 근거 텍스트로
    변환한다.

    알레르겐 정보가 없으면 빈 문자열을 반환한다.
    """

    if not allergens:
        return ""

    lines: list[str] = [
        "[식약처 향료 알레르기 표시 대상 정보]",
        (
            "아래 정보는 제품 전성분과 "
            "식약처 향료 알레르기 유발성분 "
            "표시 대상 목록을 exact match한 결과이다."
        ),
    ]

    for index, item in enumerate(
        allergens,
        start=1,
    ):
        lines.append("")
        lines.append(
            f"{index}. 성분명: "
            f"{item.query_ingredient}"
        )
        lines.append(
            f"- 공식 한글명: "
            f"{item.ingredient_kor_name}"
        )
        lines.append(
            f"- 법적 상태: "
            f"{item.legal_status}"
        )
        lines.append(
            f"- 적용 국가: "
            f"{item.jurisdiction}"
        )

        if item.cas_numbers:
            lines.append(
                f"- CAS 번호: "
                f"{', '.join(item.cas_numbers)}"
            )

        if item.rinse_off_threshold:
            lines.append(
                "- 사용 후 씻어내는 제품 "
                f"표시 기준: "
                f"{item.rinse_off_threshold}"
            )

        if item.leave_on_threshold:
            lines.append(
                "- 사용 후 씻어내지 않는 제품 "
                f"표시 기준: "
                f"{item.leave_on_threshold}"
            )

        lines.append(
            f"- 공식 출처: "
            f"{item.source_document}"
        )

        if item.source_section:
            lines.append(
                f"- 출처 위치: "
                f"{item.source_section}"
            )

    lines.extend(
        [
            "",
            "[알레르겐 정보 해석 원칙]",
            (
                "- 이 목록에 포함됐다는 사실은 "
                "향료 알레르기 유발성분의 "
                "법적 표시 대상이라는 뜻이다."
            ),
            (
                "- 표시 대상이라는 사실만으로 "
                "모든 사용자에게 알레르기 반응을 "
                "일으킨다고 단정할 수 없다."
            ),
            (
                "- 전성분표에는 실제 함량이 없으므로 "
                "표시 기준 농도를 초과했는지 "
                "판단할 수 없다."
            ),
            (
                "- 현재 데이터는 법적 표시 대상 "
                "정보이며, 접촉 알레르기·감작성의 "
                "의학적 원인을 직접 증명하지 않는다."
            ),
            (
                "- 사용자의 기존 알레르기 이력이나 "
                "패치 테스트 결과가 없으면 "
                "개인 반응의 원인이라고 단정하지 않는다."
            ),
        ]
    )

    return "\n".join(lines)