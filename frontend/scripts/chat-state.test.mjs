import assert from "node:assert/strict";
import test from "node:test";
import {
  removeAnalysisMessages,
} from "../src/utils/chat.ts";
import {
  acquireAnalysisLock,
  assembleProductAnalysisRequest,
  createAnalysisAttempt,
  createPendingAnalysisTarget,
  getBackFlowState,
  releaseAnalysisLock,
} from "../src/utils/analysisFlow.ts";
import {
  buildSkinAnalysisFields,
  getSkinPreferenceDecision,
} from "../src/utils/skin.ts";

const product = {
  product_id: "synthetic-product",
  source: "oliveyoung",
  brand_name: "테스트 브랜드",
  product_name: "합성 테스트 상품",
  category: "skincare",
  category_path: "스킨케어",
  product_url:
    "https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=synthetic-product",
  image_url: null,
  original_price: null,
  sale_price: null,
  rank: null,
  search_query: "합성 테스트 상품",
  fetched_at: "2026-01-01T00:00:00Z",
};

const option = {
  internal_option_key: "option-01",
  source_option_id: "source-option-01",
  option_name: "01호",
  raw_option_name: "01호",
  normalized_name: "01호",
  image_url: null,
  mapping_status: "matched",
  mapping_confidence: 1,
};

const emptyProfile = {
  skinType: "",
  sensitive: false,
  dehydration: false,
  barrierImpaired: false,
  concerns: [],
  customSymptom: "",
  symptomTiming: "",
  knownAllergies: "",
  productArea: "",
  customArea: "",
  currentRoutine: "",
};

test("새 상품·옵션 분석을 시작할 때 이전 분석 결과를 제거한다", () => {
  const messages = [
    {
      id: "question",
      role: "user",
      kind: "text",
      content: "질문",
      createdAt: new Date(),
    },
    {
      id: "analysis",
      role: "assistant",
      kind: "analysis",
      analysis: {},
      createdAt: new Date(),
    },
    {
      id: "options",
      role: "assistant",
      kind: "text",
      content: "옵션을 선택해 주세요.",
      createdAt: new Date(),
    },
  ];

  const result = removeAnalysisMessages(messages);

  assert.deepEqual(
    result.map((message) => message.id),
    ["question", "options"],
  );
});

test("옵션 없는 상품은 피부 선택 단계의 pending 대상으로 보존된다", () => {
  const target = createPendingAnalysisTarget(product);

  assert.equal(target.product, product);
  assert.equal(target.option, null);
  assert.equal(getBackFlowState(target), "waiting_for_product_selection");
});

test("옵션 있는 상품은 선택 옵션과 함께 pending 대상으로 보존된다", () => {
  const target = createPendingAnalysisTarget(product, option);
  const skinFields = buildSkinAnalysisFields(
    { ...emptyProfile, skinType: "oily" },
    false,
  );
  const request = assembleProductAnalysisRequest(
    product,
    "합성 질문",
    skinFields,
    {
      optionId: option.internal_option_key,
      optionName: option.option_name,
      sourceOptionId: option.source_option_id,
    },
  );

  assert.equal(getBackFlowState(target), "waiting_for_option_selection");
  assert.equal(request.internal_option_key, "option-01");
  assert.equal(request.option_name, "01호");
  assert.equal(request.source_option_id, "source-option-01");
  assert.equal(request.skin_type, null);
  assert.equal(request.skin_profile, null);
  assert.equal(request.current_routine, null);
});

test("건너뛰기는 저장된 전역 프로필을 payload에서 제외한다", () => {
  const skinFields = buildSkinAnalysisFields(
    {
      ...emptyProfile,
      skinType: "dry",
      sensitive: true,
      currentRoutine: "합성 루틴",
    },
    false,
  );

  assert.equal(skinFields.skin_type, null);
  assert.equal(skinFields.skin_profile, null);
  assert.equal(skinFields.current_routine, null);
});

test("피부 맞춤 분석은 저장된 프로필을 payload에 포함한다", () => {
  const skinFields = buildSkinAnalysisFields(
    {
      ...emptyProfile,
      skinType: "combination",
      sensitive: true,
      concerns: ["redness"],
      currentRoutine: "합성 루틴",
    },
    true,
  );

  assert.equal(skinFields.skin_type, "combination");
  assert.equal(skinFields.skin_profile.skin_type, "combination");
  assert.equal(skinFields.skin_profile.sensitive, true);
  assert.match(skinFields.current_routine, /합성 루틴/);
});

test("프로필이 없으면 입력 단계로, 있으면 분석 단계로 진행한다", () => {
  assert.equal(getSkinPreferenceDecision(emptyProfile), "collect_profile");
  assert.equal(
    getSkinPreferenceDecision({ ...emptyProfile, sensitive: true }),
    "analyze",
  );
});

test("분석 잠금은 중복 클릭에서 첫 요청만 허용한다", () => {
  const lock = { current: false };

  assert.equal(acquireAnalysisLock(lock), true);
  assert.equal(acquireAnalysisLock(lock), false);
  releaseAnalysisLock(lock);
  assert.equal(acquireAnalysisLock(lock), true);
});

test("재시도용 분석 조건은 상품·옵션·프로필 스냅샷을 유지한다", () => {
  const target = createPendingAnalysisTarget(product, option);
  const profile = {
    ...emptyProfile,
    sensitive: true,
    concerns: ["redness"],
  };
  const attempt = createAnalysisAttempt(target, true, profile);

  profile.concerns.push("itching");
  assert.equal(attempt.target.option.internal_option_key, "option-01");
  assert.deepEqual(attempt.profile.concerns, ["redness"]);
  assert.equal(attempt.useSkinProfile, true);
});
