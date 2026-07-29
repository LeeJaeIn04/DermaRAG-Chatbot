from app.allergens.mfds_repository import (
    get_mfds_fragrance_allergen_repository,
)
from app.products.allergen_mapper import (
    build_allergen_context,
    build_product_allergens,
)


def main() -> None:
    repository = (
        get_mfds_fragrance_allergen_repository()
    )

    matches = repository.find_for_ingredients(
        [
            "정제수",
            "리모넨",
            "리날룰",
            "글리세린",
        ]
    )

    allergens = build_product_allergens(
        matches
    )

    context = build_allergen_context(
        allergens
    )

    print(f"매칭 수: {len(matches)}")
    print(f"응답 모델 수: {len(allergens)}")
    print()
    print(context)

    assert len(matches) == 2
    assert len(allergens) == 2

    assert allergens[0].legal_status == (
        "labeling_required"
    )

    assert "리모넨" in context
    assert "리날룰" in context
    assert "0.01% 초과" in context
    assert "0.001% 초과" in context

    assert (
        "모든 사용자에게 알레르기 반응을 "
        "일으킨다고 단정할 수 없다"
        in context
    )

    print()
    print("allergen mapper test ok")


if __name__ == "__main__":
    main()