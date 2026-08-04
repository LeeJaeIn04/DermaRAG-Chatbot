import type {
  SkinCompatibilityNotice,
  UserSkinProfile,
} from "./chat";

export type ProductCategory =
  | "skincare"
  | "color_makeup"
  | "other"
  | "unknown";

export interface ProductCandidate {
  product_id: string;
  source: string;
  brand_name: string | null;
  product_name: string;
  category: ProductCategory;
  category_path: string | null;
  product_url: string;
  image_url: string | null;
  original_price: number | null;
  sale_price: number | null;
  rank: number | null;
  search_query: string | null;
  fetched_at: string;
}

export interface ProductSearchRequest {
  query: string;
  limit?: number;
}

export interface ProductSearchResponse {
  query: string;
  products: ProductCandidate[];
  metadata: {
    provider: string;
    result_count: number;
    search_empty: boolean;
    cache_hit: boolean;
  };
}

export interface ProductSelectionRequest {
  product_id: string;
  products: ProductCandidate[];
}

export interface ProductSelectionResponse {
  selected_product: ProductCandidate;
  next_action: string;
  requires_option_selection: boolean;
  options: ProductOption[];
  can_analyze: boolean;
  option_status:
    | "ready"
    | "not_applicable"
    | "unavailable";
  option_error: string | null;
}

export interface ProductOption {
  internal_option_key: string;
  source_option_id: string | null;
  option_name: string;
  raw_option_name: string;
  normalized_name: string;
  image_url: string | null;
  mapping_status: "matched" | "unmatched" | "ambiguous" | "unsupported";
  mapping_confidence: number;
}

export interface ProductIngredientRequest {
  product: ProductCandidate;
  option_id?: string;
  internal_option_key?: string | null;
  option_name?: string | null;
  source_option_id?: string | null;
}

export interface ProductIngredientResult {
  product_id: string;
  product_url: string;
  raw_ingredients: string;
  ingredients: string[];
  extraction_method: string;
  extraction_success: boolean;
  error_message: string | null;
}

export interface ProductIngredientResponse {
  result: ProductIngredientResult;
  cache_hit: boolean;
  cache_expired: boolean;
  extraction_performed: boolean;
}

export interface ProductAnalysisRequest {
  product: ProductCandidate;
  question: string;
  skin_type?: string | null;
  skin_profile?: UserSkinProfile | null;
  current_routine?: string | null;
  option_id?: string;
  internal_option_key?: string | null;
  option_name?: string | null;
  source_option_id?: string | null;
}

export interface ProductRegulationSource {
  query_ingredient: string;
  matched_name: string;
  match_type: "ingredient_kor_name" | "chemical_name" | "cas_no";
  regulation_type: "prohibited" | "restricted";
  category:
    | "prohibited"
    | "preservative"
    | "uv_filter"
    | "hair_dye"
    | "restricted_other";
  cas_no: string;
  chemical_name: string | null;
  max_concentration: string | null;
  product_scope: string | null;
  use_conditions: string | null;
  warning_text: string | null;
  source_id: string;
  source_authority: string;
  source_document: string;
  notice_number: string;
  notice_label: string;
  notice_date: string;
  source_section: string;
  source_table: number | null;
  source_row: number;
}

export interface ProductFragranceAllergenSource {
  query_ingredient: string;
  matched_name: string;
  match_type:
    | "ingredient_kor_name"
    | "ingredient_eng_name"
    | "inci_name"
    | "alias"
    | "cas_no";
  ingredient_kor_name: string;
  ingredient_eng_name: string | null;
  inci_name: string | null;
  cas_numbers: string[];
  aliases: string[];
  allergen_type: string;
  legal_status: string;
  jurisdiction: string;
  evidence_scope: string;
  rinse_off_threshold: string | null;
  leave_on_threshold: string | null;
  source_id: string;
  source_authority: string;
  source_document: string;
  source_document_version: string | null;
  source_document_date: string | null;
  source_section: string | null;
  source_page: number | null;
  source_row: number;
}

export interface IngredientSource {
  source?: string;
  content?: string;
  ingredient_kor_name?: string | null;
  ingredient_eng_name?: string | null;
  cas_no?: string | null;
  retrieval_type?: string | null;
  match_score?: number | null;
  query_ingredient?: string | null;
  [key: string]: unknown;
}

export interface ProductAnalysisResponse {
  product: ProductCandidate;
  answer: string;
  sources: IngredientSource[];
  metadata: Record<string, unknown>;
  ingredient_count: number;
  skin_compatibility: SkinCompatibilityNotice[];
  selected_option_key: string | null;
  selected_option_name: string | null;
  option_specific_ingredients: boolean;
  regulation_count: number;
  regulations: ProductRegulationSource[];
  allergen_count: number;
  allergens: ProductFragranceAllergenSource[];
  cache_hit: boolean;
  cache_expired: boolean;
  extraction_performed: boolean;
}
