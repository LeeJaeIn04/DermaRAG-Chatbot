import type {
  SkinConcern,
  SkinCompatibilityLevel,
  SkinCompatibilityNotice,
  SkinProfile,
  UserSkinProfile,
} from "../types/chat";

const concernLabels: Record<SkinConcern, string> = {
  dehydration: "수분 부족",
  acne_prone: "여드름·트러블",
  clogged_pores: "모공 막힘",
  excess_sebum: "과도한 피지",
  tightness: "당김",
  flaking: "각질",
  redness: "홍조",
  stinging: "따가움",
  itching: "가려움",
  barrier_impaired: "피부 장벽 약화",
};

const levelPriority: Record<SkinCompatibilityLevel, number> = {
  high: 0,
  caution: 1,
  reference: 2,
  beneficial: 3,
};

export function toUserSkinProfile(
  profile: SkinProfile,
): UserSkinProfile | null {
  const knownAllergies = profile.knownAllergies
    .split(/[,\n]/)
    .map((value) => value.trim())
    .filter(Boolean);

  const hasStructuredProfile = Boolean(
    profile.skinType ||
      profile.sensitive ||
      profile.dehydration ||
      profile.barrierImpaired ||
      profile.concerns.length ||
      knownAllergies.length,
  );

  if (!hasStructuredProfile) return null;

  return {
    skin_type: profile.skinType || null,
    sensitive: profile.sensitive,
    dehydration: profile.dehydration,
    barrier_impaired: profile.barrierImpaired,
    concerns: profile.concerns,
    known_allergies: knownAllergies,
    previous_reactions: [],
  };
}

export function hasSkinProfileData(profile: SkinProfile) {
  return Boolean(
    toUserSkinProfile(profile) ||
      profile.customSymptom.trim() ||
      profile.symptomTiming ||
      profile.productArea ||
      profile.customArea.trim() ||
      profile.currentRoutine.trim(),
  );
}

export function getSkinPreferenceDecision(profile: SkinProfile) {
  return hasSkinProfileData(profile) ? "analyze" : "collect_profile";
}

export function profileToRoutine(profile: SkinProfile) {
  const details: string[] = [];

  if (profile.currentRoutine.trim()) {
    details.push(`함께 사용하는 제품: ${profile.currentRoutine.trim()}`);
  }
  if (profile.concerns.length || profile.customSymptom.trim()) {
    details.push(
      `현재 증상: ${[
        ...profile.concerns.map((concern) => concernLabels[concern]),
        profile.customSymptom.trim(),
      ]
        .filter(Boolean)
        .join(", ")}`,
    );
  }
  if (profile.symptomTiming) {
    details.push(`증상이 나타나는 시점: ${profile.symptomTiming}`);
  }
  if (profile.knownAllergies.trim()) {
    details.push(
      `알레르기 또는 민감 성분 이력: ${profile.knownAllergies.trim()}`,
    );
  }
  const area =
    profile.productArea === "직접 입력"
      ? profile.customArea.trim()
      : profile.productArea;
  if (area) details.push(`제품 사용 부위: ${area}`);

  return details.length ? details.join("\n") : null;
}

export function buildSkinAnalysisFields(
  profile: SkinProfile | null,
  useSkinProfile: boolean,
) {
  const appliedProfile = useSkinProfile ? profile : null;

  return {
    skin_type: appliedProfile?.skinType || null,
    skin_profile: appliedProfile ? toUserSkinProfile(appliedProfile) : null,
    current_routine: appliedProfile ? profileToRoutine(appliedProfile) : null,
  };
}

export function summarizeSkinProfile(profile: SkinProfile): string[] {
  const summary: string[] = [];
  const skinTypeLabels: Record<Exclude<SkinProfile["skinType"], "">, string> = {
    normal: "중성",
    dry: "건성",
    oily: "지성",
    combination: "복합성",
  };

  if (profile.skinType) summary.push(skinTypeLabels[profile.skinType]);
  if (profile.sensitive) summary.push("민감함");
  if (profile.dehydration) summary.push("수분 부족");
  if (profile.barrierImpaired) summary.push("피부 장벽 약화");
  if (profile.concerns.length) {
    summary.push(`피부 고민 ${profile.concerns.length}개`);
  }
  if (profile.customSymptom.trim()) summary.push("피부 증상 입력됨");
  if (profile.symptomTiming) summary.push("증상 시점 입력됨");
  if (profile.knownAllergies.trim()) summary.push("알레르기 이력 입력됨");
  if (profile.productArea) summary.push("사용 부위 입력됨");
  if (profile.currentRoutine.trim()) summary.push("사용 제품 입력됨");

  return summary;
}

export function sortSkinCompatibilityNotices(
  notices: SkinCompatibilityNotice[],
) {
  return [...notices].sort(
    (left, right) =>
      levelPriority[left.level] - levelPriority[right.level],
  );
}
