import json
from pathlib import Path

import pytest

from app.products.ingredient_extractors import oliveyoung_options
from app.products.ingredient_extractors.oliveyoung_option_metadata import (
    DomOptionSnapshot,
    FlightOptionMetadata,
    FlightOptionParseResult,
    parse_flight_option_metadata,
    reconcile_dom_and_flight_options,
)
from app.products.ingredient_extractors.oliveyoung_options import (
    OPTION_BUTTON_SELECTOR,
    OPTION_LIST_SELECTOR,
    OPTION_NAME_SELECTOR,
    OPTION_ROW_BUTTON_SELECTOR,
    OPTION_ROW_SELECTOR,
    OPTION_SOLD_OUT_LABEL_SELECTOR,
    OliveYoungProductOptionExtractor,
)
from app.products.models import ProductIngredientResult
from app.products.ingredient_cache_service import _option_storage_metadata
from app.products.option_parser import make_product_option
from app.products.playwright_runtime import CollectionDeadline


FIXTURE_PATH = Path(__file__).parent / "fixtures" / (
    "oliveyoung_product_options_minimal.json"
)


def _fixture_script() -> str:
    return FIXTURE_PATH.read_text(encoding="utf-8")


def _dom_options() -> list[DomOptionSnapshot]:
    return [
        DomOptionSnapshot("[본품+리필] 17Y", False, False, None, 1),
        DomOptionSnapshot("[본품+리필] 21Y", False, False, None, 2),
        DomOptionSnapshot(
            "[본품+리필+쿠션케이스+퍼프] 21Y",
            True,
            True,
            "일시품절",
            3,
        ),
    ]


def test_parses_minimal_flight_option_metadata() -> None:
    result = parse_flight_option_metadata([_fixture_script()])

    assert result.status == "parsed"
    assert result.combination_option_flag is False
    assert [option.option_number for option in result.options] == [
        "001",
        "002",
        "020",
    ]
    assert result.options[0].standard_code == "880000000001"
    assert result.options[0].representative is True
    assert result.options[0].image_url == "https://example.test/17y.jpg"
    assert "[본품] 17Y" not in {
        option.option_name for option in result.options
    }


def test_parses_next_flight_push_string() -> None:
    payload = json.dumps(json.loads(_fixture_script()), ensure_ascii=False)
    script = f"self.__next_f.push({json.dumps([1, payload])})"

    result = parse_flight_option_metadata([script])

    assert result.status == "parsed"
    assert len(result.options) == 3


def test_flight_parser_scopes_metadata_to_requested_product() -> None:
    current = json.loads(_fixture_script())
    related = {
        "goodsNumber": "RELATED",
        "optionList": [
            {
                "goodsNumber": "RELATED",
                "optionNumber": "999",
                "optionName": "추천 상품 옵션",
                "soldOutFlag": False,
            }
        ],
    }

    result = parse_flight_option_metadata(
        [json.dumps({"current": current, "related": related})],
        product_id="A000000175954",
    )

    assert len(result.options) == 3
    assert all(option.option_number != "999" for option in result.options)


def test_reconciles_dom_order_names_ids_and_sold_out_state() -> None:
    flight = parse_flight_option_metadata([_fixture_script()])

    result = reconcile_dom_and_flight_options(_dom_options(), flight)

    assert result.status == "complete_match"
    assert result.options[2].dom.disabled is True
    assert result.options[2].dom.sold_out is True
    assert result.options[2].flight is not None
    assert result.options[2].flight.option_number == "020"


def _flight_option(
    name: str,
    number: str,
    *,
    sold_out: bool = False,
    sort_order: int = 1,
) -> FlightOptionMetadata:
    return FlightOptionMetadata(
        option_number=number,
        standard_code=f"code-{number}",
        option_name=name,
        sold_out_flag=sold_out,
        image_url=None,
        sort_order=sort_order,
        representative=False,
    )


def test_reconciles_unique_names_when_only_flight_order_differs() -> None:
    dom = [
        DomOptionSnapshot("옵션 A", False, False, None, 1),
        DomOptionSnapshot("옵션 B", True, True, "일시품절", 2),
    ]
    flight = FlightOptionParseResult(
        status="parsed",
        options=(
            _flight_option("옵션 B", "002", sold_out=True, sort_order=1),
            _flight_option("옵션 A", "001", sort_order=2),
        ),
    )

    result = reconcile_dom_and_flight_options(dom, flight)

    assert result.status == "complete_match_reordered"
    assert result.mismatch_category == "order_only_mismatch"
    assert result.safe_reorder_possible is True
    assert [item.dom.raw_option_name for item in result.options] == [
        "옵션 A", "옵션 B"
    ]
    assert [item.flight.option_number for item in result.options] == [
        "001", "002"
    ]


def test_reordered_names_use_conservative_normalization_only() -> None:
    dom = [
        DomOptionSnapshot("[단품] 21Y", False, False, None, 1),
        DomOptionSnapshot("[기획] 21Y", False, False, None, 2),
    ]
    flight = FlightOptionParseResult(
        status="parsed",
        options=(
            _flight_option("기획 21Y", "002", sort_order=1),
            _flight_option("단품 21Y", "001", sort_order=2),
        ),
    )

    result = reconcile_dom_and_flight_options(dom, flight)

    assert result.status == "complete_match_reordered"
    assert [item.flight.option_number for item in result.options] == [
        "001", "002"
    ]


def test_package_identity_is_not_removed_for_flight_reconciliation() -> None:
    dom = [
        DomOptionSnapshot("[단품] 21Y", False, False, None, 1),
        DomOptionSnapshot("[기획] 21Y", False, False, None, 2),
    ]
    flight = FlightOptionParseResult(
        status="parsed",
        options=(
            _flight_option("21Y", "001", sort_order=1),
            _flight_option("21Y", "002", sort_order=2),
        ),
    )

    result = reconcile_dom_and_flight_options(dom, flight)

    assert result.status == "mismatch"
    assert result.mismatch_category == "duplicate_name_collision"


def test_reordered_sold_out_mismatch_remains_blocked() -> None:
    dom = [
        DomOptionSnapshot("옵션 A", False, False, None, 1),
        DomOptionSnapshot("옵션 B", False, False, None, 2),
    ]
    flight = FlightOptionParseResult(
        status="parsed",
        options=(
            _flight_option("옵션 B", "002", sold_out=True, sort_order=1),
            _flight_option("옵션 A", "001", sort_order=2),
        ),
    )

    result = reconcile_dom_and_flight_options(dom, flight)

    assert result.status == "mismatch"
    assert result.mismatch_category == "sold_out_state_mismatch"


def test_duplicate_option_number_remains_blocked() -> None:
    dom = [
        DomOptionSnapshot("옵션 A", False, False, None, 1),
        DomOptionSnapshot("옵션 B", False, False, None, 2),
    ]
    flight = FlightOptionParseResult(
        status="parsed",
        options=(
            _flight_option("옵션 B", "001", sort_order=1),
            _flight_option("옵션 A", "001", sort_order=2),
        ),
    )

    result = reconcile_dom_and_flight_options(dom, flight)

    assert result.status == "mismatch"
    assert result.mismatch_category == "option_number_collision"


def test_equal_count_with_dom_and_flight_only_names_remains_blocked() -> None:
    dom = [
        DomOptionSnapshot("DOM 전용", False, False, None, 1),
        DomOptionSnapshot("공통", False, False, None, 2),
    ]
    flight = FlightOptionParseResult(
        status="parsed",
        options=(
            _flight_option("Flight 전용", "001", sort_order=1),
            _flight_option("공통", "002", sort_order=2),
        ),
    )

    result = reconcile_dom_and_flight_options(dom, flight)

    assert result.status == "mismatch"
    assert result.mismatch_category == "normalized_name_mismatch"


def test_option_collection_metadata_is_cached_but_not_publicly_serialized() -> None:
    option = make_product_option(
        "[본품+리필] 17Y",
        source_option_id="001",
    ).model_copy(
        update={
            "product_id": "A000000175954",
            "option_number": "001",
            "standard_code": "880000000001",
            "normalized_option_name": "본품+리필17y",
            "availability": "available",
            "sold_out_flag": False,
            "dom_disabled": False,
            "sort_order": 1,
            "representative": True,
            "group_path": [],
            "combination_option_flag": False,
        }
    )

    public = option.model_dump(mode="json")
    stored = _option_storage_metadata(option)

    assert "option_number" not in public
    assert "dom_disabled" not in public
    assert stored["option_number"] == "001"
    assert stored["availability"] == "available"
    assert stored["representative"] is True


def test_flight_failure_keeps_dom_options_without_official_ids() -> None:
    result = reconcile_dom_and_flight_options(
        _dom_options(),
        FlightOptionParseResult(status="failed"),
    )

    assert result.status == "partial_metadata_enrichment"
    assert len(result.options) == 3
    assert all(item.flight is None for item in result.options)


def test_mostly_sold_out_options_are_still_reconciled() -> None:
    payload = {
        "combinationOptionFlag": False,
        "optionList": [
            {
                "optionNumber": f"00{index}",
                "optionName": f"색상 {index}",
                "soldOutFlag": index != 1,
                "sortSeq": index,
            }
            for index in range(1, 5)
        ],
    }
    dom = [
        DomOptionSnapshot(
            f"색상 {index}",
            index != 1,
            index != 1,
            "일시품절" if index != 1 else None,
            index,
        )
        for index in range(1, 5)
    ]

    result = reconcile_dom_and_flight_options(
        dom,
        parse_flight_option_metadata([json.dumps(payload)]),
    )

    assert result.status == "complete_match"
    assert sum(item.dom.sold_out for item in result.options) == 3


@pytest.mark.parametrize(
    "dom_options",
    [
        _dom_options()[:2],
        [
            DomOptionSnapshot("중복 옵션", False, False, None, 1),
            DomOptionSnapshot("중복 옵션", False, False, None, 2),
            _dom_options()[2],
        ],
    ],
)
def test_count_mismatch_and_duplicate_names_are_rejected(
    dom_options,
) -> None:
    flight = parse_flight_option_metadata([_fixture_script()])

    result = reconcile_dom_and_flight_options(dom_options, flight)

    assert result.status == "mismatch"
    assert result.options == ()


class FakeLocator:
    def __init__(
        self,
        nodes=None,
        *,
        visible=True,
        on_click=None,
    ) -> None:
        self.nodes = list(nodes or [])
        self.visible = visible
        self.on_click = on_click

    @property
    def first(self):
        return self.nth(0)

    def count(self):
        return len(self.nodes)

    def nth(self, index):
        return self.nodes[index] if self.nodes else self

    def is_visible(self):
        return self.visible

    def inner_text(self):
        return self.nodes[0] if self.nodes else ""

    def scroll_into_view_if_needed(self):
        return None

    def click(self, **_kwargs):
        if self.on_click:
            self.on_click()

    def wait_for(self, **_kwargs):
        if not self.visible:
            from playwright.sync_api import TimeoutError

            raise TimeoutError("not visible")

    def locator(self, selector):
        if not self.nodes:
            return FakeLocator()
        node = self.nodes[0]
        if isinstance(node, FakeRow):
            return node.locator(selector)
        return FakeLocator()


class FakeText(FakeLocator):
    def __init__(self, text):
        super().__init__([text])


class FakeButton(FakeText):
    def __init__(self, text, *, disabled=False, on_click=None):
        super().__init__(text)
        self.disabled = disabled
        self.on_click = on_click

    def is_disabled(self):
        return self.disabled


class FakeRow:
    def __init__(self, name, *, sold_out=False):
        self.name = name
        self.sold_out = sold_out

    def locator(self, selector):
        if selector == OPTION_NAME_SELECTOR:
            return FakeLocator([FakeText(self.name)])
        if selector == OPTION_ROW_BUTTON_SELECTOR:
            return FakeLocator(
                [FakeButton(self.name, disabled=self.sold_out)]
            )
        if selector == OPTION_SOLD_OUT_LABEL_SELECTOR and self.sold_out:
            return FakeLocator([FakeText("일시품절")])
        return FakeLocator()

    def get_attribute(self, attribute):
        if attribute == "class" and self.sold_out:
            return "OptionSelector_is-soldout"
        return None

    def wait_for(self, **_kwargs):
        return None


class FakeOptionList(FakeLocator):
    def __init__(self, rows, *, visible=False):
        super().__init__([self], visible=visible)
        self.rows = rows

    def locator(self, selector):
        if selector == OPTION_ROW_SELECTOR:
            return FakeLocator(self.rows)
        return FakeLocator()


class FakeDomPage:
    def __init__(self, rows):
        self.option_list = FakeOptionList(rows, visible=False)
        self.button = FakeButton(
            "옵션을 선택해 주세요",
            on_click=self._render_options,
        )

    def _render_options(self):
        self.option_list.visible = True

    def locator(self, selector):
        if selector == OPTION_BUTTON_SELECTOR:
            return FakeLocator([self.button])
        if selector == OPTION_LIST_SELECTOR:
            return FakeLocator([self.option_list])
        return FakeLocator()


class NoOptionPage:
    def locator(self, _selector):
        return FakeLocator()


def test_missing_button_with_single_blank_flight_option_is_optionless() -> None:
    ingredient = FakeIngredientExtractor()
    extractor = OliveYoungProductOptionExtractor(ingredient)
    flight = parse_flight_option_metadata(
        [
            json.dumps(
                {
                    "optionList": [
                        {"optionNumber": "001", "optionName": "   "}
                    ]
                }
            )
        ]
    )

    options, status = extractor._collect_product_options(
        NoOptionPage(),
        product_id="A000000171650",
        flight_result=flight,
        timeout_ms=1_000,
    )

    assert options is None
    assert status == "not_applicable"


def test_dom_collection_survives_flight_failure_without_source_id() -> None:
    extractor = OliveYoungProductOptionExtractor(FakeIngredientExtractor())
    page = FakeDomPage([FakeRow("17Y"), FakeRow("21Y")])

    options, status = extractor._collect_product_options(
        page,
        product_id="A000000175954",
        flight_result=FlightOptionParseResult(status="failed"),
        timeout_ms=1_000,
    )

    assert status == "partial_metadata_enrichment"
    assert options is not None
    assert [option.source_option_id for option in options] == [None, None]
    assert all(option.availability == "available" for option in options)


class FakeIngredientExtractor:
    timeout_ms = 1_000

    def __init__(self):
        self.received_pages = []

    def _dismiss_blocking_layers(self, _page):
        return None

    def _extract_with_browser(self, browser, product_id, product_url):
        self.received_pages.append(browser.page)
        return ProductIngredientResult(
            product_id=product_id,
            product_url=product_url,
            raw_ingredients="17Y 정제수, 글리세린",
            ingredients=["17Y 정제수", "글리세린"],
            extraction_method="test",
            extraction_success=True,
        )


def test_lazy_dom_collection_includes_disabled_sold_out_option() -> None:
    ingredient = FakeIngredientExtractor()
    extractor = OliveYoungProductOptionExtractor(ingredient)
    page = FakeDomPage(
        [
            FakeRow("[본품+리필] 17Y"),
            FakeRow("[본품+리필] 21Y"),
            FakeRow(
                "[본품+리필+쿠션케이스+퍼프] 21Y",
                sold_out=True,
            ),
        ]
    )
    flight = parse_flight_option_metadata([_fixture_script()])

    options, status = extractor._collect_product_options(
        page,
        product_id="A000000175954",
        flight_result=flight,
        timeout_ms=1_000,
    )

    assert status == "complete_match"
    assert options is not None
    assert len(options) == 3
    assert options[2].availability == "temporarily_sold_out"
    assert options[2].dom_disabled is True
    assert options[2].source_option_id == "020"


class ScriptLocator:
    def all_inner_texts(self):
        return [_fixture_script()]


class EmptyLocator:
    @property
    def first(self):
        return self

    def count(self):
        return 0


class SessionPage:
    def __init__(self):
        self.goto_count = 0

    def goto(self, *_args, **_kwargs):
        self.goto_count += 1

    def locator(self, selector):
        return ScriptLocator() if selector == "script" else EmptyLocator()


def test_options_and_ingredients_use_same_page_session(monkeypatch) -> None:
    page = SessionPage()
    ingredient = FakeIngredientExtractor()
    extractor = OliveYoungProductOptionExtractor(ingredient)
    selected_option = make_product_option("17Y")
    monkeypatch.setattr(
        extractor,
        "_collect_product_options",
        lambda *_args, **_kwargs: ([selected_option], "complete_match"),
    )
    monkeypatch.setattr(extractor, "_close_option_list", lambda _page: None)

    def run_once(operation, **_kwargs):
        return operation(page, CollectionDeadline.start(10_000))

    monkeypatch.setattr(oliveyoung_options, "run_browser_operation", run_once)

    result = extractor.extract(
        "A000000175954",
        "https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do"
        "?goodsNo=A000000175954",
    )

    assert result.status == "collected"
    assert ingredient.received_pages == [page]
    assert page.goto_count == 1
    assert not hasattr(extractor, "_collect_review_options")
