import type {
  SkinCompatibilityLevel,
  SkinCompatibilityNotice,
  SkinProfile,
  UserSkinProfile,
} from "../types/chat";

const levelPriority: Record<SkinCompatibilityLevel, number> = {
  high: 0,
  caution: 1,
  reference: 2,
  beneficial: 3,
};

export function toUserSkinProfile(
  profile: SkinProfile,
): UserSkinProfile | null {
  if (!profile.skinType) return null;

  const knownAllergies = profile.knownAllergies
    .split(/[,\n]/)
    .map((value) => value.trim())
    .filter(Boolean);

  return {
    skin_type: profile.skinType,
    sensitive: profile.sensitive,
    dehydration: profile.dehydration,
    barrier_impaired: profile.barrierImpaired,
    concerns: profile.concerns,
    known_allergies: knownAllergies,
    previous_reactions: [],
  };
}

export function sortSkinCompatibilityNotices(
  notices: SkinCompatibilityNotice[],
) {
  return [...notices].sort(
    (left, right) =>
      levelPriority[left.level] - levelPriority[right.level],
  );
}
