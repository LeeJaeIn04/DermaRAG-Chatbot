from fastapi.testclient import TestClient

from app import main
from app.products.errors import ProductCollectionRetryLaterError
from app.products.models import ProductCandidate
from app.products.option_models import (
    OptionMappingDiagnostics,
    ProductOptionPreparationResult,
)
from app.products.option_parser import make_product_option


def product() -> ProductCandidate:
    return ProductCandidate(
        product_id="A000000241210",
        source="oliveyoung",
        product_name="합성 옵션 매핑 테스트 상품",
        category="color_makeup",
        product_url=(
            "https://www.oliveyoung.co.kr/store/goods/"
            "getGoodsDetail.do?goodsNo=A000000241210"
        ),
    )


def selection_payload() -> dict[str, object]:
    candidate = product()
    return {
        "product_id": candidate.product_id,
        "products": [candidate.model_dump(mode="json")],
    }


def test_first_mapping_failure_returns_public_unavailable_state(
    monkeypatch,
) -> None:
    def mapping_failed(_product):
        return ProductOptionPreparationResult(
            requires_option_selection=False,
            can_analyze=False,
            status="mapping_failed",
            error_message="internal unmatched parser detail",
            mapping_diagnostics=OptionMappingDiagnostics(
                collected_option_count=3,
                matched_count=2,
                unmatched_count=1,
            ),
        )

    monkeypatch.setattr(
        main.product_option_service,
        "prepare_product",
        mapping_failed,
    )
    response = TestClient(main.app).post(
        "/products/select",
        json=selection_payload(),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["next_action"] == "product_data_unavailable"
    assert payload["option_status"] == "unavailable"
    assert payload["requires_option_selection"] is False
    assert payload["options"] == []
    assert payload["can_analyze"] is False
    assert payload["option_error"] == (
        "현재 이 상품의 옵션별 전성분 정보를 정확히 확인할 수 없습니다. "
        "다른 상품을 선택해 주세요."
    )
    serialized = response.text
    for internal_value in (
        "mapping_failed",
        "unmatched",
        "ambiguous",
        "unsupported",
        "parser",
        "collected_option_count",
    ):
        assert internal_value not in serialized


def test_queue_backoff_remains_distinct_409_domain_error(
    monkeypatch,
) -> None:
    def retry_later(_product):
        raise ProductCollectionRetryLaterError()

    monkeypatch.setattr(
        main.product_option_service,
        "prepare_product",
        retry_later,
    )
    response = TestClient(main.app).post(
        "/products/select",
        json=selection_payload(),
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": {
            "code": "PRODUCT_COLLECTION_RETRY_LATER",
            "message": (
                "상품 정보를 다시 확인 중입니다. 잠시 후 다시 시도해 주세요."
            ),
        }
    }


def test_ready_response_exposes_one_canonical_option_without_internal_sources(
    monkeypatch,
) -> None:
    canonical = make_product_option(
        "[기획] 23호 누카다미아",
        source_option_id="primary",
    ).model_copy(
        update={
            "option_name": "23 누카다미아",
            "mapping_status": "matched",
            "source_option_names": [
                "[기획] 23호 누카다미아",
                "단품/23 누카다미아",
            ],
            "source_option_ids": ["primary", "duplicate"],
        }
    )

    monkeypatch.setattr(
        main.product_option_service,
        "prepare_product",
        lambda _product: ProductOptionPreparationResult(
            requires_option_selection=True,
            options=[canonical],
            can_analyze=True,
            status="ready",
        ),
    )
    response = TestClient(main.app).post(
        "/products/select",
        json=selection_payload(),
    )

    assert response.status_code == 200
    options = response.json()["options"]
    assert len(options) == 1
    assert options[0]["option_name"] == "23 누카다미아"
    assert "source_option_names" not in options[0]
    assert "source_option_ids" not in options[0]
    assert "ambiguous" not in response.text


def test_ready_response_with_collection_status_exposes_option_status(
    monkeypatch,
) -> None:
    """Step 4: collection_status=ready일 때도 옵션별 status/
    analysis_available이 응답에 노출된다."""

    canonical = make_product_option(
        "19호", source_option_id="19"
    ).model_copy(
        update={
            "mapping_status": "matched",
            "status": "ready",
            "analysis_available": True,
        }
    )
    monkeypatch.setattr(
        main.product_option_service,
        "prepare_product",
        lambda _product: ProductOptionPreparationResult(
            requires_option_selection=True,
            options=[canonical],
            can_analyze=True,
            status="ready",
            collection_status="ready",
        ),
    )
    response = TestClient(main.app).post(
        "/products/select",
        json=selection_payload(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["collection_status"] == "ready"
    assert body["option_status"] == "ready"
    assert body["options"][0]["status"] == "ready"
    assert body["options"][0]["analysis_available"] is True


def test_partial_response_exposes_ready_and_non_ready_options(
    monkeypatch,
) -> None:
    """Step 4: collection_status=partial이면 can_analyze는 True고,
    ready/non-ready 옵션이 모두 응답에 남으며 각각의 status/
    analysis_available이 정확히 노출된다. 내부 diagnostics는
    노출되지 않는다."""

    ready_option = make_product_option(
        "19호", source_option_id="19"
    ).model_copy(
        update={
            "mapping_status": "matched",
            "status": "ready",
            "analysis_available": True,
        }
    )
    non_ready_option = make_product_option(
        "21호", source_option_id="21"
    ).model_copy(
        update={
            "mapping_status": "unmatched",
            "status": "unmapped",
            "analysis_available": False,
        }
    )

    monkeypatch.setattr(
        main.product_option_service,
        "prepare_product",
        lambda _product: ProductOptionPreparationResult(
            requires_option_selection=True,
            options=[ready_option, non_ready_option],
            can_analyze=True,
            status="mapping_failed",
            collection_status="partial",
            mapping_diagnostics=OptionMappingDiagnostics(
                collected_option_count=2,
                matched_count=1,
                unmatched_count=1,
            ),
        ),
    )
    response = TestClient(main.app).post(
        "/products/select",
        json=selection_payload(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["can_analyze"] is True
    assert body["collection_status"] == "partial"
    assert body["option_status"] == "partial"
    assert body["requires_option_selection"] is True

    options_by_name = {
        option["option_name"]: option for option in body["options"]
    }
    assert options_by_name["19호"]["status"] == "ready"
    assert options_by_name["19호"]["analysis_available"] is True
    assert options_by_name["21호"]["status"] == "unmapped"
    assert options_by_name["21호"]["analysis_available"] is False

    # 내부 diagnostics(collected_option_count 등)는 API에 노출되지
    # 않는다.
    for internal_value in (
        "collected_option_count",
        "mapping_diagnostics",
    ):
        assert internal_value not in response.text
