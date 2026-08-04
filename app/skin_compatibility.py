from app.schemas import UserSkinProfile
from app.skin_rule_schemas import SkinCompatibilityNotice
from app.skin_rules import (
    find_rules_for_ingredient,
    get_rule_sources,
    normalize_ingredient_name,
)

def build_active_skin_profiles(
    profile: UserSkinProfile,
) -> set[str]:
    active_profiles: set[str] = set()

    if profile.skin_type:
        active_profiles.add(profile.skin_type)

    if (
        profile.skin_type == "oily"
        and profile.dehydration
    ):
        active_profiles.add(
            "dehydrated_oily"
        )

    if profile.sensitive:
        active_profiles.add(
            "sensitive"
        )

    if "acne_prone" in profile.concerns:
        active_profiles.add(
            "acne_prone"
        )

    if (
        profile.barrier_impaired
        or "barrier_impaired" in profile.concerns
    ):
        active_profiles.add(
            "barrier_impaired"
        )

    return active_profiles


def has_previous_ingredient_reaction(
    ingredient_name: str,
    profile: UserSkinProfile,
) -> bool:
    """
    사용자가 과거 같은 성분에 반응했다고 입력했는지 검사한다.
    """
    target = normalize_ingredient_name(
        ingredient_name
    )

    if not target:
        return False

    for reaction in profile.previous_reactions:
        if not reaction.ingredient_name:
            continue

        reaction_name = normalize_ingredient_name(
            reaction.ingredient_name
        )

        if reaction_name == target:
            return True

    return False


def evaluate_ingredient_for_skin(
    ingredient_name: str,
    profile: UserSkinProfile,
) -> list[SkinCompatibilityNotice]:
    """
    하나의 제품 성분을 사용자 피부 정보와 비교한다.
    """
    active_profiles = build_active_skin_profiles(
        profile
    )

    rules = find_rules_for_ingredient(
        ingredient_name
    )

    sources = get_rule_sources()

    notices: list[SkinCompatibilityNotice] = []

    for rule in rules:
        caution_matches = (
            active_profiles
            & set(rule.caution_for)
        )

        beneficial_matches = (
            active_profiles
            & set(rule.beneficial_for)
        )

        previous_reaction = (
            has_previous_ingredient_reaction(
                ingredient_name,
                profile,
            )
        )

        if (
            not caution_matches
            and not beneficial_matches
            and not previous_reaction
        ):
            continue

        if previous_reaction:
            level = "high"
            reason = (
                "사용자가 과거 동일 성분에 "
                "반응한 이력이 있습니다."
            )

        elif caution_matches:
            level = "caution"
            reason = rule.user_message_ko

        else:
            level = "beneficial"
            reason = rule.user_message_ko

        source_titles: list[str] = []
        source_urls: list[str] = []

        for source_id in rule.source_ids:
            source = sources.get(source_id)

            if source is None:
                continue

            source_titles.append(source.title)
            source_urls.append(source.url)

        notices.append(
            SkinCompatibilityNotice(
                ingredient_name=ingredient_name,
                rule_id=rule.rule_id,
                category=rule.display_name_ko,
                level=level,
                matched_profiles=sorted(
                    caution_matches
                    or beneficial_matches
                ),
                possible_concerns=(
                    rule.possible_concerns
                ),
                reason=reason,
                condition=rule.condition,
                evidence_level=(
                    rule.evidence_level
                ),
                source_titles=source_titles,
                source_urls=source_urls,
            )
        )

    return notices

def evaluate_product_ingredients(
    ingredients: list[str],
    profile: UserSkinProfile,
) -> list[SkinCompatibilityNotice]:
    """
    선택한 제품 옵션의 전체 성분을 평가한다.
    """
    notices: list[SkinCompatibilityNotice] = []

    for ingredient_name in ingredients:
        ingredient_notices = (
            evaluate_ingredient_for_skin(
                ingredient_name,
                profile,
            )
        )

        notices.extend(ingredient_notices)

    return sort_compatibility_notices(notices)


def sort_compatibility_notices(
    notices: list[SkinCompatibilityNotice],
) -> list[SkinCompatibilityNotice]:
    """
    사용자에게 중요한 결과부터 보여주도록 정렬한다.
    """
    priority = {
        "high": 0,
        "caution": 1,
        "reference": 2,
        "beneficial": 3,
    }

    return sorted(
        notices,
        key=lambda notice: (
            priority[notice.level],
            notice.ingredient_name,
        ),
    )
