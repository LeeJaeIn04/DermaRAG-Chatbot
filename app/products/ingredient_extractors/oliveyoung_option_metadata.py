from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal

from app.products.option_parser import normalize_option_label


FlightParseStatus = Literal["parsed", "failed"]
MetadataMatchStatus = Literal[
    "complete_match",
    "partial_metadata_enrichment",
    "mismatch",
]


@dataclass(frozen=True)
class FlightOptionMetadata:
    option_number: str | None
    standard_code: str | None
    option_name: str
    sold_out_flag: bool | None
    image_url: str | None
    sort_order: int | None
    representative: bool | None
    group_path: tuple[str, ...] = ()


@dataclass(frozen=True)
class FlightOptionParseResult:
    status: FlightParseStatus
    options: tuple[FlightOptionMetadata, ...] = ()
    combination_option_flag: bool | None = None


@dataclass(frozen=True)
class DomOptionSnapshot:
    raw_option_name: str
    disabled: bool | None
    has_sold_out_class: bool
    sold_out_label: str | None
    sort_order: int

    @property
    def sold_out(self) -> bool:
        return self.has_sold_out_class or (
            self.sold_out_label is not None
            and "일시품절" in self.sold_out_label
        )


@dataclass(frozen=True)
class ReconciledOption:
    dom: DomOptionSnapshot
    flight: FlightOptionMetadata | None


@dataclass(frozen=True)
class OptionReconciliationResult:
    status: MetadataMatchStatus
    options: tuple[ReconciledOption, ...]


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {"true", "y", "yes", "1"}:
            return True
        if normalized in {"false", "n", "no", "0"}:
            return False
    if isinstance(value, int) and value in {0, 1}:
        return bool(value)
    return None


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _image_url(option: dict[str, object]) -> str | None:
    for key in (
        "imageUrl",
        "optionImageUrl",
        "goodsOptionImageUrl",
        "image",
    ):
        value = option.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            for nested_key in ("url", "imageUrl", "src"):
                nested = _optional_text(value.get(nested_key))
                if nested:
                    return nested

    images = option.get("goodsOptionImageList")
    if isinstance(images, list):
        for image in images:
            if not isinstance(image, dict):
                continue
            for key in ("imageUrl", "url", "src"):
                nested = _optional_text(image.get(key))
                if nested:
                    return nested
    return None


def _group_path(option: dict[str, object]) -> tuple[str, ...]:
    raw = option.get("combinationOptionName")
    if isinstance(raw, str):
        return (raw.strip(),) if raw.strip() else ()
    if not isinstance(raw, list):
        return ()
    return tuple(
        text
        for item in raw
        if (text := _optional_text(item)) is not None
    )


def _walk(value: object):
    yield value
    if isinstance(value, dict):
        for nested in value.values():
            yield from _walk(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _walk(nested)


def _balanced_json_objects(value: str):
    start: int | None = None
    depth = 0
    in_string = False
    escaped = False
    for index, character in enumerate(value):
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character == "{":
            if depth == 0:
                start = index
            depth += 1
        elif character == "}" and depth:
            depth -= 1
            if depth == 0 and start is not None:
                yield value[start:index + 1]
                start = None


def _decoded_values(script_text: str) -> list[object]:
    values: list[object] = []
    stripped = script_text.strip()
    candidates = [stripped]
    marker = "self.__next_f.push("
    if stripped.startswith(marker) and stripped.endswith(")"):
        candidates.append(stripped[len(marker):-1])

    for candidate in candidates:
        try:
            decoded = json.loads(candidate)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        values.append(decoded)
        for nested in _walk(decoded):
            if isinstance(nested, str) and "optionNumber" in nested:
                for object_text in _balanced_json_objects(nested):
                    try:
                        values.append(json.loads(object_text))
                    except (ValueError, json.JSONDecodeError):
                        continue

    if "optionNumber" in stripped:
        for object_text in _balanced_json_objects(stripped):
            try:
                values.append(json.loads(object_text))
            except (ValueError, json.JSONDecodeError):
                continue
    return values


def parse_flight_option_metadata(
    script_texts: list[str],
    *,
    product_id: str | None = None,
) -> FlightOptionParseResult:
    option_dicts: list[tuple[str | None, dict[str, object]]] = []
    combination_flags: list[tuple[str | None, bool]] = []

    def collect(value: object, inherited_product_id: str | None = None):
        if isinstance(value, dict):
            current_product_id = (
                _optional_text(value.get("goodsNumber"))
                or _optional_text(value.get("goodsNo"))
                or inherited_product_id
            )
            combination_flag = _optional_bool(
                value.get("combinationOptionFlag")
            )
            if combination_flag is not None:
                combination_flags.append(
                    (current_product_id, combination_flag)
                )
            if "optionNumber" in value and "optionName" in value:
                option_dicts.append((current_product_id, value))
            for nested in value.values():
                collect(nested, current_product_id)
        elif isinstance(value, list):
            for nested in value:
                collect(nested, inherited_product_id)

    for script_text in script_texts:
        for decoded in _decoded_values(script_text):
            collect(decoded)

    if product_id:
        exact_options = [
            option
            for owner, option in option_dicts
            if owner == product_id
        ]
        option_dicts_only = exact_options or [
            option for owner, option in option_dicts if owner is None
        ]
        exact_flags = [
            flag
            for owner, flag in combination_flags
            if owner == product_id
        ]
        unscoped_flags = [
            flag
            for owner, flag in combination_flags
            if owner is None
        ]
        combination_option_flag = next(
            iter(exact_flags or unscoped_flags),
            None,
        )
    else:
        option_dicts_only = [option for _, option in option_dicts]
        combination_option_flag = next(
            (flag for _, flag in combination_flags),
            None,
        )

    if not option_dicts_only:
        return FlightOptionParseResult(status="failed")

    unique: dict[tuple[str | None, str, int | None], FlightOptionMetadata] = {}
    for option in option_dicts_only:
        option_name = _optional_text(option.get("optionName")) or ""
        metadata = FlightOptionMetadata(
            option_number=_optional_text(option.get("optionNumber")),
            standard_code=_optional_text(option.get("standardCode")),
            option_name=option_name,
            sold_out_flag=_optional_bool(option.get("soldOutFlag")),
            image_url=_image_url(option),
            sort_order=_optional_int(
                option.get("sortSeq", option.get("sortOrder"))
            ),
            representative=_optional_bool(
                option.get("representFlag", option.get("representative"))
            ),
            group_path=_group_path(option),
        )
        key = (
            metadata.option_number,
            normalize_option_label(metadata.option_name),
            metadata.sort_order,
        )
        unique[key] = metadata

    options = tuple(
        sorted(
            unique.values(),
            key=lambda option: (
                option.sort_order is None,
                option.sort_order or 0,
                option.option_number or "",
            ),
        )
    )
    return FlightOptionParseResult(
        status="parsed",
        options=options,
        combination_option_flag=combination_option_flag,
    )


def reconcile_dom_and_flight_options(
    dom_options: list[DomOptionSnapshot],
    flight_result: FlightOptionParseResult,
) -> OptionReconciliationResult:
    if flight_result.status == "failed":
        return OptionReconciliationResult(
            status="partial_metadata_enrichment",
            options=tuple(
                ReconciledOption(dom=option, flight=None)
                for option in dom_options
            ),
        )

    flight_options = list(flight_result.options)
    if len(dom_options) != len(flight_options):
        return OptionReconciliationResult(status="mismatch", options=())

    dom_names = [
        normalize_option_label(option.raw_option_name)
        for option in dom_options
    ]
    flight_names = [
        normalize_option_label(option.option_name)
        for option in flight_options
    ]
    if (
        len(set(dom_names)) != len(dom_names)
        or len(set(flight_names)) != len(flight_names)
        or dom_names != flight_names
    ):
        return OptionReconciliationResult(status="mismatch", options=())

    reconciled: list[ReconciledOption] = []
    for dom, flight in zip(dom_options, flight_options, strict=True):
        if (
            flight.sold_out_flag is not None
            and dom.sold_out != flight.sold_out_flag
        ):
            return OptionReconciliationResult(status="mismatch", options=())
        reconciled.append(ReconciledOption(dom=dom, flight=flight))
    return OptionReconciliationResult(
        status="complete_match",
        options=tuple(reconciled),
    )
