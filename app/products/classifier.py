from app.products.models import ProductCategory


COLOR_MAKEUP_KEYWORDS = (
    "쿠션",
    "파운데이션",
    "비비크림",
    "비비 크림",
    "씨씨크림",
    "씨씨 크림",
    "컨실러",
    "프라이머",
    "메이크업 베이스",
    "톤업 베이스",
    "블러셔",
    "치크",
    "하이라이터",
    "브론저",
    "쉐딩",
    "아이섀도",
    "아이 섀도",
    "섀도우",
    "마스카라",
    "아이라이너",
    "아이 라이너",
    "아이브로우",
    "아이 브로우",
    "브로우",
    "립스틱",
    "립틴트",
    "립 틴트",
    "틴트",
    "립글로스",
    "립 글로스",
    "립라이너",
    "립 라이너",
    "립펜슬",
    "립 펜슬",
    "컬러 립밤",
)


# 스킨케어 상품을 나타내는 키워드
SKINCARE_KEYWORDS = (
    "스킨",
    "토너",
    "에센스",
    "세럼",
    "앰플",
    "로션",
    "에멀전",
    "크림",
    "수분크림",
    "아이크림",
    "아이 크림",
    "미스트",
    "오일",
    "마스크팩",
    "마스크 팩",
    "시트마스크",
    "시트 마스크",
    "패드",
    "토너패드",
    "토너 패드",
    "선크림",
    "선 크림",
    "선로션",
    "선 로션",
    "선스틱",
    "선 스틱",
    "선세럼",
    "선 세럼",
    "자외선차단제",
    "자외선 차단제",
    "클렌저",
    "클렌징폼",
    "클렌징 폼",
    "클렌징오일",
    "클렌징 오일",
    "클렌징밤",
    "클렌징 밤",
    "클렌징워터",
    "클렌징 워터",
    "필링",
    "스크럽",
)


# 현재 DermaRAG의 분석 중심 대상이 아닌 상품
OTHER_KEYWORDS = (
    "샴푸",
    "린스",
    "트리트먼트",
    "헤어팩",
    "헤어 팩",
    "헤어스프레이",
    "헤어 스프레이",
    "바디워시",
    "바디 워시",
    "바디로션",
    "바디 로션",
    "핸드크림",
    "핸드 크림",
    "향수",
    "퍼퓸",
    "칫솔",
    "치약",
    "영양제",
    "유산균",
    "비타민",
)


# 쇼핑몰에서 제공하는 카테고리 경로가 있다면
# 상품명보다 카테고리 경로를 우선해서 사용한다.
COLOR_CATEGORY_KEYWORDS = (
    "메이크업",
    "베이스메이크업",
    "베이스 메이크업",
    "아이메이크업",
    "아이 메이크업",
    "립메이크업",
    "립 메이크업",
    "색조",
)


SKINCARE_CATEGORY_KEYWORDS = (
    "스킨케어",
    "선케어",
    "선 케어",
    "클렌징",
    "마스크팩",
    "마스크 팩",
)


OTHER_CATEGORY_KEYWORDS = (
    "헤어케어",
    "헤어 케어",
    "바디케어",
    "바디 케어",
    "향수",
    "건강식품",
    "구강용품",
)


def normalize_product_text(value: str | None) -> str:
    if value is None:
        return ""

    return " ".join(
        value.strip().lower().split()
    )


def contains_any_keyword(
    text: str,
    keywords: tuple[str, ...],
) -> bool:

    return any(
        keyword.lower() in text
        for keyword in keywords
    )


def classify_product_category(
    product_name: str,
    category_path: str | None = None,
) -> ProductCategory:

    normalized_name = normalize_product_text(
        product_name
    )
    normalized_category = normalize_product_text(
        category_path
    )

    if normalized_category:
        if contains_any_keyword(
            normalized_category,
            COLOR_CATEGORY_KEYWORDS,
        ):
            return "color_makeup"

        if contains_any_keyword(
            normalized_category,
            SKINCARE_CATEGORY_KEYWORDS,
        ):
            return "skincare"

        if contains_any_keyword(
            normalized_category,
            OTHER_CATEGORY_KEYWORDS,
        ):
            return "other"
        
    has_color_expression = contains_any_keyword(
        normalized_name,
        (
            "컬러",
            "틴티드",
            "틴티드 컬러",
        ),
    )

    has_lip_expression = contains_any_keyword(
        normalized_name,
        (
            "립",
            "입술",
        ),
    )

    if has_color_expression and has_lip_expression:
        return "color_makeup"

    if contains_any_keyword(
        normalized_name,
        COLOR_MAKEUP_KEYWORDS,
    ):
        return "color_makeup"

    if contains_any_keyword(
        normalized_name,
        SKINCARE_KEYWORDS,
    ):
        return "skincare"

    if contains_any_keyword(
        normalized_name,
        OTHER_KEYWORDS,
    ):
        return "other"

    return "unknown"


def get_next_action(
    category: ProductCategory,
) -> str:

    if category == "skincare":
        return "extract_ingredients"

    if category == "color_makeup":
        return "select_product_option"

    return "manual_review"