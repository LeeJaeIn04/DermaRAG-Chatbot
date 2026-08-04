import json
import warnings
from collections import Counter
from typing import Any
from unittest.mock import patch

warnings.filterwarnings(
    "ignore",
    message=(
        "Using `httpx` with `starlette.testclient` "
        "is deprecated.*"
    ),
)

from fastapi.testclient import TestClient

import app.main as app_main
from app.langsmith_client import (
    create_langsmith_client,
    run_with_langsmith_auth_help,
)
from app.products.ingredient_cache_service import (
    ProductIngredientResolution,
)
from app.products.models import ProductIngredientResult
from app.products.schemas import ProductAnalysisResponse


DATASET_NAME = "DermaRAG Product Analysis Baseline v1"

TEST_CLIENT = TestClient(app_main.app)

REGULATION_SOURCE_FIELDS = {
    "source_id",
    "source_authority",
    "source_document",
    "notice_number",
    "notice_label",
    "source_section",
    "source_table",
    "source_row",
}

ALLERGEN_SOURCE_FIELDS = {
    "source_id",
    "source_authority",
    "source_document",
    "source_section",
    "source_row",
    "cas_numbers",
}


def _make_resolution(
    *,
    product: Any,
    ingredients: list[str],
) -> ProductIngredientResolution:
    return ProductIngredientResolution(
        result=ProductIngredientResult(
            product_id=product.product_id,
            product_url=product.product_url,
            raw_ingredients=", ".join(ingredients),
            ingredients=ingredients,
            extraction_method="evaluation_fixture",
            extraction_success=True,
            error_message=None,
        ),
        cache_hit=True,
        cache_expired=False,
        extraction_performed=False,
    )


def _regulation_source_complete(
    item: dict[str, Any],
) -> bool:
    if not REGULATION_SOURCE_FIELDS.issubset(item):
        return False

    required_values = [
        item.get("source_id"),
        item.get("source_authority"),
        item.get("source_document"),
        item.get("notice_number"),
        item.get("notice_label"),
        item.get("source_section"),
        item.get("source_row"),
    ]

    return all(
        value is not None
        and bool(str(value).strip())
        for value in required_values
    )


def _regulation_basis_complete(
    item: dict[str, Any],
) -> bool:
    if item.get("regulation_type") not in {
        "restricted",
        "prohibited",
    }:
        return False

    basis_values = [
        item.get("max_concentration"),
        item.get("product_scope"),
        item.get("use_conditions"),
        item.get("warning_text"),
    ]

    return any(
        value is not None
        and bool(str(value).strip())
        for value in basis_values
    )


def _allergen_source_complete(
    item: dict[str, Any],
) -> bool:
    if not ALLERGEN_SOURCE_FIELDS.issubset(item):
        return False

    required_values = [
        item.get("source_id"),
        item.get("source_authority"),
        item.get("source_document"),
        item.get("source_section"),
        item.get("source_row"),
    ]

    return (
        all(
            value is not None
            and bool(str(value).strip())
            for value in required_values
        )
        and isinstance(
            item.get("cas_numbers"),
            list,
        )
        and bool(item.get("cas_numbers"))
    )


def product_analysis_target(
    inputs: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate the real API route with only network and LLM calls replaced."""

    case_id = str(
        inputs.get("case_id", "case")
    ).strip()
    ingredients = [
        str(ingredient).strip()
        for ingredient in inputs.get(
            "ingredients",
            [],
        )
        if str(ingredient).strip()
    ]

    product_id = (
        "EVAL-"
        + case_id.upper().replace("_", "-")
    )
    product_url = (
        "https://example.invalid/products/"
        + product_id
    )

    product = {
        "product_id": product_id,
        "source": "evaluation",
        "brand_name": "Synthetic",
        "product_name": "합성 평가 상품",
        "category": "skincare",
        "category_path": "evaluation",
        "product_url": product_url,
        "fetched_at": "2026-01-01T00:00:00Z",
    }

    def fake_get_or_extract(
        **kwargs: Any,
    ) -> ProductIngredientResolution:
        return _make_resolution(
            product=kwargs["product"],
            ingredients=ingredients,
        )

    def fake_invoke_derma_rag(
        request: Any,
        *,
        api_endpoint: str = "/chat",
    ) -> dict[str, Any]:
        return {
            "answer": "결정론적 합성 상품 분석 결과",
            "sources": [],
            "metadata": {
                "ingredient_count": len(
                    request.ingredients
                ),
                "api_endpoint": api_endpoint,
            },
            "skin_compatibility": [],
        }

    with (
        patch.object(
            app_main.ingredient_cache_service,
            "get_or_extract",
            fake_get_or_extract,
        ),
        patch.object(
            app_main,
            "invoke_derma_rag",
            fake_invoke_derma_rag,
        ),
    ):
        response = TEST_CLIENT.post(
            "/products/analyze",
            json={
                "product": product,
                "question": "합성 상품 성분을 분석해 주세요.",
            },
        )

    try:
        body = response.json()
    except ValueError:
        body = {}

    schema_valid = False
    try:
        ProductAnalysisResponse.model_validate(
            body
        )
        schema_valid = True
    except ValueError:
        pass

    json_serializable = False
    try:
        json.dumps(
            body,
            ensure_ascii=False,
        )
        json_serializable = True
    except (TypeError, ValueError):
        pass

    regulations = body.get("regulations")
    allergens = body.get("allergens")
    regulations_is_list = isinstance(
        regulations,
        list,
    )
    allergens_is_list = isinstance(
        allergens,
        list,
    )
    regulation_items = (
        regulations
        if regulations_is_list
        else []
    )
    allergen_items = (
        allergens
        if allergens_is_list
        else []
    )

    required_response_fields = set(
        ProductAnalysisResponse.model_fields
    )
    required_fields_present = (
        required_response_fields.issubset(body)
        and isinstance(body.get("product"), dict)
        and {
            "product_id",
            "source",
            "product_name",
            "product_url",
        }.issubset(body.get("product", {}))
    )

    empty_array_fields = [
        field
        for field, value in (
            ("regulations", regulations),
            ("allergens", allergens),
        )
        if isinstance(value, list)
        and not value
    ]

    return {
        "status_code": response.status_code,
        "schema_valid": schema_valid,
        "json_serializable": json_serializable,
        "ingredient_count": body.get(
            "ingredient_count"
        ),
        "regulation_count": body.get(
            "regulation_count"
        ),
        "regulations_length": len(
            regulation_items
        ),
        "allergen_count": body.get(
            "allergen_count"
        ),
        "allergens_length": len(
            allergen_items
        ),
        "regulations_is_list": (
            regulations_is_list
        ),
        "allergens_is_list": (
            allergens_is_list
        ),
        "regulations": [
            {
                "matched_name": item.get(
                    "matched_name"
                ),
                "regulation_type": item.get(
                    "regulation_type"
                ),
                "max_concentration": item.get(
                    "max_concentration"
                ),
                "product_scope": item.get(
                    "product_scope"
                ),
                "use_conditions": item.get(
                    "use_conditions"
                ),
                "warning_text": item.get(
                    "warning_text"
                ),
                "source_id": item.get(
                    "source_id"
                ),
            }
            for item in regulation_items
        ],
        "regulation_source_flags": [
            _regulation_source_complete(item)
            for item in regulation_items
        ],
        "regulation_basis_flags": [
            _regulation_basis_complete(item)
            for item in regulation_items
        ],
        "allergens": [
            {
                "ingredient_kor_name": item.get(
                    "ingredient_kor_name"
                ),
                "source_id": item.get(
                    "source_id"
                ),
            }
            for item in allergen_items
        ],
        "allergen_source_flags": [
            _allergen_source_complete(item)
            for item in allergen_items
        ],
        "allergen_thresholds": [
            {
                "rinse_off_threshold": item.get(
                    "rinse_off_threshold"
                ),
                "leave_on_threshold": item.get(
                    "leave_on_threshold"
                ),
            }
            for item in allergen_items
        ],
        "empty_array_fields": empty_array_fields,
        "required_fields_present": (
            required_fields_present
        ),
    }


def _dict_counter(
    values: list[dict[str, Any]],
) -> Counter[str]:
    return Counter(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
        )
        for value in values
    )


def status_code_correct(
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> bool:
    return outputs.get(
        "status_code"
    ) == reference_outputs.get(
        "expected_status_code"
    )


def response_schema_valid(
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> bool:
    del reference_outputs
    return (
        outputs.get("schema_valid") is True
        and outputs.get(
            "json_serializable"
        ) is True
    )


def regulation_count_consistent(
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> bool:
    expected_count = reference_outputs.get(
        "expected_regulation_count"
    )
    return (
        outputs.get("regulation_count")
        == outputs.get("regulations_length")
        == expected_count
    )


def allergen_count_consistent(
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> bool:
    expected_count = reference_outputs.get(
        "expected_allergen_count"
    )
    return (
        outputs.get("allergen_count")
        == outputs.get("allergens_length")
        == expected_count
    )


def expected_regulations_correct(
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> bool:
    return _dict_counter(
        outputs.get("regulations", [])
    ) == _dict_counter(
        reference_outputs.get(
            "expected_regulations",
            [],
        )
    )


def expected_allergens_correct(
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> bool:
    return _dict_counter(
        outputs.get("allergens", [])
    ) == _dict_counter(
        reference_outputs.get(
            "expected_allergens",
            [],
        )
    )


def regulation_sources_complete(
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> bool:
    expected_count = int(
        reference_outputs.get(
            "expected_regulation_count",
            0,
        )
    )
    flags = outputs.get(
        "regulation_source_flags",
        [],
    )
    return (
        len(flags) == expected_count
        and (
            expected_count == 0
            or all(flags)
        )
    )


def regulation_basis_complete(
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> bool:
    expected_count = int(
        reference_outputs.get(
            "expected_regulation_count",
            0,
        )
    )
    flags = outputs.get(
        "regulation_basis_flags",
        [],
    )
    return (
        len(flags) == expected_count
        and (
            expected_count == 0
            or all(flags)
        )
    )


def allergen_sources_complete(
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> bool:
    expected_count = int(
        reference_outputs.get(
            "expected_allergen_count",
            0,
        )
    )
    flags = outputs.get(
        "allergen_source_flags",
        [],
    )
    return (
        len(flags) == expected_count
        and (
            expected_count == 0
            or all(flags)
        )
    )


def allergen_thresholds_correct(
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> bool:
    return _dict_counter(
        outputs.get(
            "allergen_thresholds",
            [],
        )
    ) == _dict_counter(
        reference_outputs.get(
            "expected_allergen_thresholds",
            [],
        )
    )


def empty_arrays_correct(
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> bool:
    return (
        outputs.get("regulations_is_list")
        is True
        and outputs.get("allergens_is_list")
        is True
        and Counter(
            outputs.get(
                "empty_array_fields",
                [],
            )
        )
        == Counter(
            reference_outputs.get(
                "expected_empty_fields",
                [],
            )
        )
    )


def required_fields_present(
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> bool:
    del reference_outputs
    return (
        outputs.get(
            "required_fields_present"
        ) is True
    )


def product_analysis_case_correct(
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> bool:
    return all(
        evaluator(
            outputs,
            reference_outputs,
        )
        for evaluator in [
            status_code_correct,
            response_schema_valid,
            regulation_count_consistent,
            allergen_count_consistent,
            expected_regulations_correct,
            expected_allergens_correct,
            regulation_sources_complete,
            regulation_basis_complete,
            allergen_sources_complete,
            allergen_thresholds_correct,
            empty_arrays_correct,
            required_fields_present,
        ]
    )


EVALUATORS = [
    status_code_correct,
    response_schema_valid,
    regulation_count_consistent,
    allergen_count_consistent,
    expected_regulations_correct,
    expected_allergens_correct,
    regulation_sources_complete,
    regulation_basis_complete,
    allergen_sources_complete,
    allergen_thresholds_correct,
    empty_arrays_correct,
    required_fields_present,
    product_analysis_case_correct,
]


def run_evaluation() -> None:
    client = create_langsmith_client()

    results = client.evaluate(
        product_analysis_target,
        data=DATASET_NAME,
        evaluators=EVALUATORS,
        experiment_prefix=(
            "derma-rag-product-analysis-baseline-v1"
        ),
        metadata={
            "evaluation_scope": (
                "product_analysis_response"
            ),
            "uses_llm": False,
            "baseline_version": "v1",
            "evaluation_level": "api_contract",
        },
        max_concurrency=1,
    )

    print(results)


def main() -> None:
    run_with_langsmith_auth_help(
        run_evaluation
    )


if __name__ == "__main__":
    main()
