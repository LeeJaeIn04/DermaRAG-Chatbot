import type { ProductCandidate } from "../types/product";

export interface ProductAnalysisEligibility {
  canAnalyze: boolean;
  reason: string | null;
}

export function createProductSearchQuery(question: string) {
  const normalized = question
    .trim()
    .replace(/[“”"']/g, "")
    .replace(/\s+/g, " ");

  const withoutIntentSuffix = normalized
    .replace(
      /\s*(?:이|가|은|는)?\s*(?:민감성\s*피부에\s*)?(?:괜찮은지|잘\s*맞는지)\s*(?:알려\s*줘|알려주세요|분석해\s*줘|분석해주세요)?[?.!]*$/u,
      "",
    )
    .replace(
      /(?:을|를)?\s*(?:성분을?\s*)?(?:분석|확인)(?:해\s*(?:줘|주세요))?[?.!]*$/u,
      "",
    )
    .trim();

  return withoutIntentSuffix || normalized;
}

export function getProductAnalysisEligibility(
  product: ProductCandidate,
): ProductAnalysisEligibility {
  if (product.source !== "oliveyoung") {
    return {
      canAnalyze: false,
      reason: "올리브영에서 제공된 상품만 분석할 수 있어요.",
    };
  }

  const productUrl = product.product_url.trim();
  if (!productUrl) {
    return {
      canAnalyze: false,
      reason: "상품 상세 주소가 없어 분석할 수 없어요.",
    };
  }

  try {
    const parsedUrl = new URL(productUrl);
    const hostname = parsedUrl.hostname.toLowerCase();
    const isHttpUrl =
      parsedUrl.protocol === "https:" || parsedUrl.protocol === "http:";
    const isOliveYoung =
      hostname === "oliveyoung.co.kr" ||
      hostname.endsWith(".oliveyoung.co.kr");

    if (!isHttpUrl || !isOliveYoung) {
      return {
        canAnalyze: false,
        reason: "올리브영 상품 주소가 확인되지 않았어요.",
      };
    }
  } catch {
    return {
      canAnalyze: false,
      reason: "상품 상세 주소 형식이 올바르지 않아요.",
    };
  }

  return {
    canAnalyze: true,
    reason: null,
  };
}
