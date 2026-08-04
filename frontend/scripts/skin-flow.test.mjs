import assert from "node:assert/strict";
import test from "node:test";
import {
  hasSkinProfileData,
  sortSkinCompatibilityNotices,
  toUserSkinProfile,
} from "../src/utils/skin.ts";

const emptyProfile = {
  skinType: "",
  sensitive: false,
  dehydration: false,
  barrierImpaired: false,
  concerns: [],
  knownAllergies: "",
  customSymptom: "",
  symptomTiming: "",
  productArea: "",
  customArea: "",
  currentRoutine: "",
};

test("피부 타입을 선택하면 구조화 프로필을 만든다", () => {
  const profile = toUserSkinProfile({
    ...emptyProfile,
    skinType: "oily",
    sensitive: true,
    dehydration: true,
    concerns: ["excess_sebum", "tightness"],
    knownAllergies: "리모넨, 리날룰\n향료",
  });

  assert.deepEqual(profile, {
    skin_type: "oily",
    sensitive: true,
    dehydration: true,
    barrier_impaired: false,
    concerns: ["excess_sebum", "tightness"],
    known_allergies: ["리모넨", "리날룰", "향료"],
    previous_reactions: [],
  });
});

test("피부 정보가 모두 비어 있으면 프로필을 전송하지 않는다", () => {
  assert.equal(toUserSkinProfile(emptyProfile), null);
  assert.equal(hasSkinProfileData(emptyProfile), false);
});

test("피부 타입 없이 민감 상태만 입력해도 구조화 프로필을 만든다", () => {
  assert.deepEqual(
    toUserSkinProfile({ ...emptyProfile, sensitive: true }),
    {
      skin_type: null,
      sensitive: true,
      dehydration: false,
      barrier_impaired: false,
      concerns: [],
      known_allergies: [],
      previous_reactions: [],
    },
  );
});

test("피부 타입 없이 고민만 입력해도 구조화 프로필을 만든다", () => {
  const result = toUserSkinProfile({
    ...emptyProfile,
    concerns: ["redness"],
  });

  assert.equal(result.skin_type, null);
  assert.deepEqual(result.concerns, ["redness"]);
});

test("피부 타입 없이 알레르기 이력만 입력해도 구조화 프로필을 만든다", () => {
  const result = toUserSkinProfile({
    ...emptyProfile,
    knownAllergies: "리모넨, 리날룰",
  });

  assert.equal(result.skin_type, null);
  assert.deepEqual(result.known_allergies, ["리모넨", "리날룰"]);
});

test("피부 타입 없이 여러 상태를 함께 전달한다", () => {
  const result = toUserSkinProfile({
    ...emptyProfile,
    sensitive: true,
    dehydration: true,
    barrierImpaired: true,
    concerns: ["itching"],
  });

  assert.deepEqual(result, {
    skin_type: null,
    sensitive: true,
    dehydration: true,
    barrier_impaired: true,
    concerns: ["itching"],
    known_allergies: [],
    previous_reactions: [],
  });
});

test("피부 적합성 결과를 지정된 우선순위로 정렬한다", () => {
  const makeNotice = (level) => ({
    ingredient_name: level,
    rule_id: level,
    category: "테스트",
    level,
    matched_profiles: [],
    possible_concerns: [],
    reason: "테스트",
    condition: "",
    evidence_level: "reference",
    source_titles: [],
    source_urls: [],
  });

  const sorted = sortSkinCompatibilityNotices([
    makeNotice("beneficial"),
    makeNotice("reference"),
    makeNotice("high"),
    makeNotice("caution"),
  ]);

  assert.deepEqual(
    sorted.map((notice) => notice.level),
    ["high", "caution", "reference", "beneficial"],
  );
  assert.deepEqual(sortSkinCompatibilityNotices([]), []);
});
