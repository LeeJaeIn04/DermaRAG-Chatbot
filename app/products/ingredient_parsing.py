def split_raw_ingredient_text(
    raw_ingredients: str,
) -> list[str]:
    """괄호 안 또는 숫자 사이 쉼표는 보존해 전성분을 분리한다."""

    tokens: list[str] = []
    current: list[str] = []
    depth = 0

    for index, char in enumerate(raw_ingredients):
        if char in "([":
            depth += 1
            current.append(char)
        elif char in ")]":
            depth = max(0, depth - 1)
            current.append(char)
        elif char == "," and depth == 0:
            previous = (
                raw_ingredients[index - 1] if index > 0 else ""
            )
            following = (
                raw_ingredients[index + 1]
                if index + 1 < len(raw_ingredients)
                else ""
            )
            if previous.isdigit() and following.isdigit():
                current.append(char)
                continue
            tokens.append("".join(current))
            current = []
        else:
            current.append(char)

    tokens.append("".join(current))
    return [token.strip() for token in tokens if token.strip()]
