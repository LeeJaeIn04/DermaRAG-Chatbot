import type {
  ProductAnalysisRequest,
  ProductAnalysisResponse,
  ProductIngredientRequest,
  ProductIngredientResponse,
  ProductSearchRequest,
  ProductSearchResponse,
  ProductSelectionRequest,
  ProductSelectionResponse,
} from "../types/product";
import { apiRequest } from "./client";

export function searchProducts(request: ProductSearchRequest) {
  return apiRequest<ProductSearchResponse>("/products/search", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export function selectProduct(request: ProductSelectionRequest) {
  return apiRequest<ProductSelectionResponse>("/products/select", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export function extractIngredients(request: ProductIngredientRequest) {
  return apiRequest<ProductIngredientResponse>(
    "/products/extract-ingredients",
    {
      method: "POST",
      body: JSON.stringify(request),
    },
  );
}

export function analyzeProduct(request: ProductAnalysisRequest) {
  return apiRequest<ProductAnalysisResponse>("/products/analyze", {
    method: "POST",
    body: JSON.stringify(request),
  });
}
