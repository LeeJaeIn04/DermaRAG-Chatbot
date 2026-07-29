from __future__ import annotations

from app.products.schemas import (
    ProductRegulationSource,
)
from app.safety.schemas import (
    IngredientRegulationMatch,
)


def build_product_regulations(
    matches: list[IngredientRegulationMatch],
) -> list[ProductRegulationSource]:
    """
    식약처 Repository의 내부 규제 일치 모델을
    상품 분석 API 응답 모델로 변환한다.
    """

    results: list[
        ProductRegulationSource
    ] = []

    for match in matches:
        regulation = match.regulation

        results.append(
            ProductRegulationSource(
                query_ingredient=(
                    match.query_ingredient
                ),
                matched_name=match.matched_name,
                match_type=match.match_type,
                regulation_type=(
                    regulation.regulation_type
                ),
                category=regulation.category,
                cas_no=regulation.cas_no,
                chemical_name=(
                    regulation.chemical_name
                ),
                max_concentration=(
                    regulation.max_concentration
                ),
                product_scope=(
                    regulation.product_scope
                ),
                use_conditions=(
                    regulation.use_conditions
                ),
                warning_text=(
                    regulation.warning_text
                ),
                source_authority=(
                    regulation.source_authority
                ),
                source_document=(
                    regulation.source_document
                ),
                notice_number=(
                    regulation.notice_number
                ),
                notice_date=(
                    regulation.notice_date
                ),
                source_section=(
                    regulation.source_section
                ),
            )
        )

    return results

def build_regulation_context(
    regulations: list[ProductRegulationSource],
) -> str:
    """
    식약처 규제 정보를 Gemini 프롬프트에 전달할
    근거 텍스트로 변환한다.

    규제 정보가 없으면 빈 문자열을 반환한다.
    """

    if not regulations:
        return ""

    lines: list[str] = [
        "[식약처 화장품 규제 정보]",
        (
            "아래 정보는 제품 전성분과 "
            "식약처 규제 원료 목록을 "
            "exact match한 결과이다."
        ),
    ]

    for index, item in enumerate(
        regulations,
        start=1,
    ):
        lines.append("")
        lines.append(
            f"{index}. 성분명: "
            f"{item.query_ingredient}"
        )
        lines.append(
            f"- 규제 유형: "
            f"{item.regulation_type}"
        )
        lines.append(
            f"- 규제 분류: {item.category}"
        )

        if item.max_concentration:
            lines.append(
                f"- 최대 사용한도: "
                f"{item.max_concentration}"
            )

        if item.product_scope:
            lines.append(
                f"- 적용 제품 범위: "
                f"{item.product_scope}"
            )

        if item.use_conditions:
            lines.append(
                f"- 사용 조건: "
                f"{item.use_conditions}"
            )

        if item.warning_text:
            lines.append(
                f"- 주의 문구: "
                f"{item.warning_text}"
            )

        lines.append(
            f"- 공식 출처: "
            f"{item.source_document} "
            f"{item.source_section}"
        )
        lines.append(
            f"- 고시 번호: "
            f"{item.notice_number}"
        )

    lines.extend(
        [
            "",
            "[규제 정보 해석 원칙]",
            (
                "- restricted는 해당 성분이 "
                "무조건 위험하다는 뜻이 아니다."
            ),
            (
                "- restricted는 허용 용도, "
                "최대 농도 또는 사용 조건이 "
                "정해진 성분이라는 뜻이다."
            ),
            (
                "- 전성분표에는 실제 함량이 없으므로 "
                "최대 사용한도 초과 여부를 판단할 수 없다."
            ),
            (
                "- prohibited exact match가 있을 때만 "
                "화장품에 사용할 수 없는 원료라고 설명한다."
            ),
        ]
    )

    return "\n".join(lines)