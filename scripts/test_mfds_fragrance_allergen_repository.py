from app.allergens.mfds_repository import get_mfds_fragrance_allergen_repository


def main() -> None:
    repository = (
        get_mfds_fragrance_allergen_repository()
    )

    print(
        f"레코드 수: "
        f"{len(repository.records)}"
    )

    test_ingredients = [
        "정제수",
        "리모넨",
        "리날룰",
        "벤질알코올",
        "글리세린",
    ]

    matches = (
        repository.find_for_ingredients(
            test_ingredients
        )
    )

    print(
        f"매칭 수: {len(matches)}"
    )

    for match in matches:
        allergen = match.allergen

        print(
            f"- query={match.query_ingredient}, "
            f"matched={match.matched_name}, "
            f"type={match.match_type}, "
            f"cas={allergen.cas_numbers}, "
            f"rinse_off={allergen.rinse_off_threshold}, "
            f"leave_on={allergen.leave_on_threshold}"
        )

    assert len(repository.records) == 25
    assert len(matches) == 3

    matched_names = {
        match.allergen.ingredient_kor_name
        for match in matches
    }

    assert matched_names == {
        "리모넨",
        "리날룰",
        "벤질알코올",
    }

    print("repository test ok")


if __name__ == "__main__":
    main()