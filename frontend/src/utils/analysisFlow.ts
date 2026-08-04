import type {
  ChatFlowState,
  SkinProfile,
  UserSkinProfile,
} from "../types/chat";
import type {
  ProductAnalysisRequest,
  ProductCandidate,
  ProductOption,
} from "../types/product";

export interface PendingAnalysisTarget {
  product: ProductCandidate;
  option: ProductOption | null;
}

export interface AnalysisAttempt {
  target: PendingAnalysisTarget;
  useSkinProfile: boolean;
  profile: SkinProfile | null;
}

interface AnalysisLock {
  current: boolean;
}

export function acquireAnalysisLock(lock: AnalysisLock) {
  if (lock.current) return false;
  lock.current = true;
  return true;
}

export function releaseAnalysisLock(lock: AnalysisLock) {
  lock.current = false;
}

export function createPendingAnalysisTarget(
  product: ProductCandidate,
  option: ProductOption | null = null,
): PendingAnalysisTarget {
  return { product, option };
}

export function getBackFlowState(
  target: PendingAnalysisTarget,
): Extract<
  ChatFlowState,
  "waiting_for_product_selection" | "waiting_for_option_selection"
> {
  return target.option
    ? "waiting_for_option_selection"
    : "waiting_for_product_selection";
}

export function createAnalysisAttempt(
  target: PendingAnalysisTarget,
  useSkinProfile: boolean,
  profile: SkinProfile | null,
): AnalysisAttempt {
  return {
    target,
    useSkinProfile,
    profile:
      useSkinProfile && profile
        ? { ...profile, concerns: [...profile.concerns] }
        : null,
  };
}

export function assembleProductAnalysisRequest(
  product: ProductCandidate,
  question: string,
  skinFields: {
    skin_type: string | null;
    skin_profile: UserSkinProfile | null;
    current_routine: string | null;
  },
  option?: {
    optionId?: string;
    optionName?: string | null;
    sourceOptionId?: string | null;
  },
): ProductAnalysisRequest {
  return {
    product,
    question,
    ...skinFields,
    option_id: option?.optionId || "",
    internal_option_key: option?.optionId || null,
    option_name: option?.optionName || null,
    source_option_id: option?.sourceOptionId || null,
  };
}
