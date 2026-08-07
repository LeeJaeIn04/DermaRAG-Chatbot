import assert from "node:assert/strict";
import test from "node:test";
import {
  isOptionAnalyzable,
  selectDefaultAnalyzableOption,
} from "../src/utils/products.ts";

function makeOption(overrides) {
  return {
    internal_option_key: "option-key",
    source_option_id: "source-option",
    option_name: "옵션",
    raw_option_name: "옵션",
    normalized_name: "옵션",
    image_url: null,
    mapping_status: "matched",
    mapping_confidence: 1,
    status: "ready",
    analysis_available: true,
    ...overrides,
  };
}

test("all-ready: 모든 옵션이 ready면 첫 옵션이 기본 선택되고 전부 분석 가능하다", () => {
  const options = [
    makeOption({ internal_option_key: "19", option_name: "19호" }),
    makeOption({ internal_option_key: "21", option_name: "21호" }),
  ];

  assert.equal(
    selectDefaultAnalyzableOption(options)?.internal_option_key,
    "19",
  );
  assert.ok(options.every(isOptionAnalyzable));
});

test("partial 혼합 상태: ready 옵션만 분석 가능하고 기본 선택도 그 옵션이다", () => {
  const options = [
    makeOption({
      internal_option_key: "19",
      option_name: "19호",
      status: "ready",
      analysis_available: true,
    }),
    makeOption({
      internal_option_key: "21",
      option_name: "21호",
      mapping_status: "unmatched",
      status: "unmapped",
      analysis_available: false,
    }),
  ];

  assert.equal(isOptionAnalyzable(options[0]), true);
  assert.equal(isOptionAnalyzable(options[1]), false);
  assert.equal(
    selectDefaultAnalyzableOption(options)?.internal_option_key,
    "19",
  );
});

test("첫 옵션이 non-ready여도 기본 선택은 첫 번째 ready 옵션이다", () => {
  const options = [
    makeOption({
      internal_option_key: "19",
      option_name: "19호",
      mapping_status: "ambiguous",
      status: "ambiguous",
      analysis_available: false,
    }),
    makeOption({
      internal_option_key: "20",
      option_name: "20호",
      mapping_status: "unmatched",
      status: "empty",
      analysis_available: false,
    }),
    makeOption({
      internal_option_key: "21",
      option_name: "21호",
      status: "ready",
      analysis_available: true,
    }),
  ];

  const defaultOption = selectDefaultAnalyzableOption(options);
  assert.equal(defaultOption?.internal_option_key, "21");
});

test("ready 옵션이 0개면 기본 선택은 없다(null)", () => {
  const options = [
    makeOption({
      internal_option_key: "19",
      mapping_status: "unmatched",
      status: "unmapped",
      analysis_available: false,
    }),
    makeOption({
      internal_option_key: "21",
      mapping_status: "ambiguous",
      status: "ambiguous",
      analysis_available: false,
    }),
  ];

  assert.equal(selectDefaultAnalyzableOption(options), null);
  assert.ok(options.every((option) => !isOptionAnalyzable(option)));
});

test("기존 정상 흐름: 옵션이 하나뿐이고 ready면 그 옵션이 그대로 선택된다", () => {
  const options = [makeOption({ internal_option_key: "single" })];

  const defaultOption = selectDefaultAnalyzableOption(options);
  assert.equal(defaultOption?.internal_option_key, "single");
  assert.equal(isOptionAnalyzable(defaultOption), true);
});
