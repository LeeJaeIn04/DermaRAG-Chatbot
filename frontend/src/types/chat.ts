import type {
  ProductAnalysisResponse,
  ProductCandidate,
  ProductOption,
} from "./product";

export type ChatFlowState =
  | "idle"
  | "classifying_intent"
  | "searching_products"
  | "waiting_for_product_selection"
  | "waiting_for_option_selection"
  | "fetching_ingredients"
  | "analyzing_product"
  | "completed"
  | "error";

export type SkinType =
  | "normal"
  | "dry"
  | "oily"
  | "combination";

export type SkinConcern =
  | "dehydration"
  | "acne_prone"
  | "clogged_pores"
  | "excess_sebum"
  | "tightness"
  | "flaking"
  | "redness"
  | "stinging"
  | "itching"
  | "barrier_impaired";

export interface PreviousReaction {
  ingredient_name?: string | null;
  product_name?: string | null;
  reaction: string;
  severity: "low" | "moderate" | "high";
}

export interface UserSkinProfile {
  skin_type: SkinType;
  sensitive: boolean;
  dehydration: boolean;
  barrier_impaired: boolean;
  concerns: SkinConcern[];
  known_allergies: string[];
  previous_reactions: PreviousReaction[];
}

export interface SkinProfile {
  skinType: SkinType | "";
  sensitive: boolean;
  dehydration: boolean;
  barrierImpaired: boolean;
  concerns: SkinConcern[];
  customSymptom: string;
  symptomTiming: string;
  knownAllergies: string;
  productArea: string;
  customArea: string;
  currentRoutine: string;
}

export type ChatMessage =
  | {
      id: string;
      role: "user" | "assistant";
      kind: "text";
      content: string;
      createdAt: Date;
    }
  | {
      id: string;
      role: "assistant";
      kind: "options";
      content: string;
      product: ProductCandidate;
      options: ProductOption[];
      createdAt: Date;
    }
  | {
      id: string;
      role: "assistant";
      kind: "products";
      content: string;
      searchQuery: string;
      products: ProductCandidate[];
      createdAt: Date;
    }
  | {
      id: string;
      role: "assistant";
      kind: "analysis";
      analysis: ProductAnalysisResponse;
      createdAt: Date;
    }
  | {
      id: string;
      role: "assistant";
      kind: "error";
      content: string;
      detail?: string;
      createdAt: Date;
    };

export interface ChatRequest {
  question: string;
  skin_type?: string | null;
  skin_profile?: UserSkinProfile | null;
  ingredient_list?: string | null;
  current_routine?: string | null;
  ingredients?: string[];
}

export interface ChatResponse {
  answer: string;
  sources: Array<Record<string, unknown>>;
  metadata: Record<string, unknown>;
  skin_compatibility: SkinCompatibilityNotice[];
}

export type SkinCompatibilityLevel =
  | "high"
  | "caution"
  | "reference"
  | "beneficial";

export interface SkinCompatibilityNotice {
  ingredient_name: string;
  rule_id: string;
  category: string;
  level: SkinCompatibilityLevel;
  matched_profiles: string[];
  possible_concerns: string[];
  reason: string;
  condition: string;
  evidence_level: string;
  source_titles: string[];
  source_urls: string[];
}
