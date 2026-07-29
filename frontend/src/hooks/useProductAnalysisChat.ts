import { useCallback, useMemo, useRef, useState } from "react";
import { ApiError } from "../api/client";
import {
  analyzeProduct,
  searchProducts,
  selectProduct,
} from "../api/products";
import type {
  ChatFlowState,
  ChatMessage,
  SkinConcern,
  SkinProfile,
} from "../types/chat";
import type {
  ProductAnalysisRequest,
  ProductCandidate,
  ProductOption,
} from "../types/product";
import {
  createProductSearchQuery,
  getProductAnalysisEligibility,
} from "../utils/products";
import { toUserSkinProfile } from "../utils/skin";
import { removeAnalysisMessages } from "../utils/chat";

const initialAssistantMessage: ChatMessage = {
  id: "welcome",
  role: "assistant",
  kind: "text",
  content:
    "안녕하세요. **DermaRAG**입니다.\n\n궁금한 화장품이나 피부 반응을 입력해 주세요.",
  createdAt: new Date(),
};

function createId(prefix: string) {
  return `${prefix}-${crypto.randomUUID()}`;
}

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

function profileToRoutine(profile: SkinProfile) {
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
  const area = profile.productArea === "직접 입력"
    ? profile.customArea.trim()
    : profile.productArea;
  if (area) details.push(`제품 사용 부위: ${area}`);

  return details.length ? details.join("\n") : null;
}

export function buildProductAnalysisRequest(
  product: ProductCandidate,
  question: string,
  profile: SkinProfile,
  option?: {
    optionId?: string;
    optionName?: string | null;
    sourceOptionId?: string | null;
  },
): ProductAnalysisRequest {
  const eligibility = getProductAnalysisEligibility(product);
  if (!eligibility.canAnalyze) {
    throw new ApiError(
      eligibility.reason || "선택한 상품의 올리브영 주소를 확인할 수 없어요.",
      400,
      `product_id=${product.product_id}, source=${product.source}, product_url=${product.product_url}`,
    );
  }

  return {
    // 검색 결과의 ProductCandidate 참조와 모든 필드를 그대로 유지한다.
    product,
    question,
    skin_type: profile.skinType || null,
    skin_profile: toUserSkinProfile(profile),
    current_routine: profileToRoutine(profile),
    option_id: option?.optionId || "",
    internal_option_key: option?.optionId || null,
    option_name: option?.optionName || null,
    source_option_id: option?.sourceOptionId || null,
  };
}

export function useProductAnalysisChat(profile: SkinProfile) {
  const [messages, setMessages] = useState<ChatMessage[]>([
    initialAssistantMessage,
  ]);
  const [flowState, setFlowState] = useState<ChatFlowState>("idle");
  const [currentQuestion, setCurrentQuestion] = useState("");
  const [selectedProduct, setSelectedProduct] =
    useState<ProductCandidate | null>(null);
  const [selectedOption, setSelectedOption] =
    useState<ProductOption | null>(null);
  const busyRef = useRef(false);

  const appendMessage = useCallback((message: ChatMessage) => {
    setMessages((current) => [...current, message]);
  }, []);

  const clearAnalysisMessages = useCallback(() => {
    setMessages(removeAnalysisMessages);
  }, []);

  const reportError = useCallback(
    (error: unknown) => {
      const apiError =
        error instanceof ApiError
          ? error
          : new ApiError(
              "처리 중 오류가 발생했어요. 잠시 후 다시 시도해 주세요.",
              0,
              error instanceof Error ? error.message : String(error),
            );

      setFlowState("error");
      clearAnalysisMessages();
      appendMessage({
        id: createId("error"),
        role: "assistant",
        kind: "error",
        content: apiError.message,
        detail: apiError.detail,
        createdAt: new Date(),
      });
    },
    [appendMessage, clearAnalysisMessages],
  );

  const submitQuestion = useCallback(
    async (question: string) => {
      const normalizedQuestion = question.trim();
      if (!normalizedQuestion || busyRef.current) return;

      busyRef.current = true;
      clearAnalysisMessages();
      setCurrentQuestion(normalizedQuestion);
      setSelectedProduct(null);
      setSelectedOption(null);
      appendMessage({
        id: createId("user"),
        role: "user",
        kind: "text",
        content: normalizedQuestion,
        createdAt: new Date(),
      });

      try {
        setFlowState("classifying_intent");
        await new Promise((resolve) => window.setTimeout(resolve, 250));
        setFlowState("searching_products");

        const searchQuery = createProductSearchQuery(normalizedQuestion);
        const response = await searchProducts({
          query: searchQuery,
          limit: 6,
        });

        if (!response.products.length) {
          setFlowState("idle");
          appendMessage({
            id: createId("empty"),
            role: "assistant",
            kind: "text",
            content:
              "검색된 상품이 없습니다. 브랜드와 상품명을 조금 더 구체적으로 입력해 주세요.",
            createdAt: new Date(),
          });
          return;
        }

        appendMessage({
          id: createId("products"),
          role: "assistant",
          kind: "products",
          content: "아래 상품 중 분석할 제품을 선택해 주세요.",
          searchQuery: response.query,
          products: response.products,
          createdAt: new Date(),
        });
        setFlowState("waiting_for_product_selection");
      } catch (error) {
        reportError(error);
      } finally {
        busyRef.current = false;
      }
    },
    [appendMessage, clearAnalysisMessages, reportError],
  );

  const runAnalysis = useCallback(
    async (product: ProductCandidate, option?: ProductOption) => {
      let analysisTimer: number | undefined;
      try {
        analysisTimer = window.setTimeout(() => {
          setFlowState("analyzing_product");
        }, 900);

        const analysisRequest = buildProductAnalysisRequest(
          product,
          currentQuestion,
          profile,
          option
            ? {
                optionId: option.internal_option_key,
                optionName: option.option_name,
                sourceOptionId: option.source_option_id,
              }
            : undefined,
        );

        if (import.meta.env.DEV) {
          console.info("[DermaRAG] POST /products/analyze", {
            product_id: analysisRequest.product.product_id,
            source: analysisRequest.product.source,
            product_url: analysisRequest.product.product_url,
            internal_option_key: analysisRequest.internal_option_key,
            option_name: analysisRequest.option_name,
            source_option_id: analysisRequest.source_option_id,
          });
        }

        const analysis = await analyzeProduct(analysisRequest);
        window.clearTimeout(analysisTimer);
        setFlowState("completed");
        appendMessage({
          id: createId("analysis"),
          role: "assistant",
          kind: "analysis",
          analysis,
          createdAt: new Date(),
        });
      } catch (error) {
        if (analysisTimer) window.clearTimeout(analysisTimer);
        reportError(error);
      }
    },
    [
      appendMessage,
      currentQuestion,
      profile,
      reportError,
    ],
  );

  const chooseProduct = useCallback(
    async (
      product: ProductCandidate,
      candidates: ProductCandidate[],
    ) => {
      if (busyRef.current || flowState !== "waiting_for_product_selection") {
        return;
      }

      const eligibility = getProductAnalysisEligibility(product);
      if (!eligibility.canAnalyze) {
        appendMessage({
          id: createId("unavailable"),
          role: "assistant",
          kind: "text",
          content:
            eligibility.reason ||
            "현재 이 상품은 전성분 분석을 진행할 수 없어요.",
          createdAt: new Date(),
        });
        return;
      }

      busyRef.current = true;
      clearAnalysisMessages();
      // 검색 응답의 ProductCandidate 객체를 재구성하지 않고 그대로 보존한다.
      setSelectedProduct(product);
      setSelectedOption(null);
      if (import.meta.env.DEV) {
        console.info("[DermaRAG] selected product from /products/search", {
          product_id: product.product_id,
          source: product.source,
          product_url: product.product_url,
        });
      }
      appendMessage({
        id: createId("selection"),
        role: "user",
        kind: "text",
        content: `${product.brand_name ? `${product.brand_name} ` : ""}${product.product_name}을(를) 분석해 주세요.`,
        createdAt: new Date(),
      });
      setFlowState("fetching_ingredients");

      try {
        const selection = await selectProduct({
          product_id: product.product_id,
          products: candidates,
        });

        if (!selection.can_analyze) {
          setFlowState("idle");
          appendMessage({
            id: createId("option-unavailable"),
            role: "assistant",
            kind: "text",
            content:
              selection.option_error ||
              "이 상품의 옵션별 전성분을 정확히 구분하지 못했습니다. 현재는 옵션별 분석을 진행할 수 없습니다.",
            createdAt: new Date(),
          });
          return;
        }

        if (selection.requires_option_selection) {
          appendMessage({
            id: createId("options"),
            role: "assistant",
            kind: "options",
            content:
              "이 상품에는 여러 색상 또는 호수가 있습니다. 분석할 옵션을 선택해 주세요.",
            product,
            options: selection.options,
            createdAt: new Date(),
          });
          setFlowState("waiting_for_option_selection");
          return;
        }

        await runAnalysis(product);
      } catch (error) {
        reportError(error);
      } finally {
        busyRef.current = false;
      }
    },
    [
      appendMessage,
      clearAnalysisMessages,
      flowState,
      reportError,
      runAnalysis,
    ],
  );

  const chooseOption = useCallback(
    async (product: ProductCandidate, option: ProductOption) => {
      if (
        busyRef.current ||
        flowState !== "waiting_for_option_selection" ||
        option.mapping_status !== "matched"
      ) {
        return;
      }

      busyRef.current = true;
      clearAnalysisMessages();
      setSelectedOption(option);
      setFlowState("fetching_ingredients");
      appendMessage({
        id: createId("option-selection"),
        role: "user",
        kind: "text",
        content: `${option.option_name} 옵션을 분석해 주세요.`,
        createdAt: new Date(),
      });

      if (import.meta.env.DEV) {
        console.info("[DermaRAG] selected option", {
          product_id: product.product_id,
          internal_option_key: option.internal_option_key,
          source_option_id: option.source_option_id,
          option_name: option.option_name,
        });
      }

      try {
        await runAnalysis(product, option);
      } finally {
        busyRef.current = false;
      }
    },
    [
      appendMessage,
      clearAnalysisMessages,
      flowState,
      runAnalysis,
    ],
  );

  const startNewChat = useCallback(() => {
    if (busyRef.current) return;
    setMessages([
      {
        ...initialAssistantMessage,
        createdAt: new Date(),
      },
    ]);
    setFlowState("idle");
    setCurrentQuestion("");
    setSelectedProduct(null);
    setSelectedOption(null);
  }, []);

  const recentAnalyses = useMemo(
    () =>
      messages
        .filter(
          (
            message,
          ): message is Extract<ChatMessage, { kind: "analysis" }> =>
            message.kind === "analysis",
        )
        .map((message) => ({
          id: message.id,
          productName: message.analysis.product.product_name,
        }))
        .reverse(),
    [messages],
  );

  return {
    messages,
    flowState,
    selectedProduct,
    selectedOption,
    recentAnalyses,
    submitQuestion,
    chooseProduct,
    chooseOption,
    startNewChat,
    isBusy:
      flowState === "classifying_intent" ||
      flowState === "searching_products" ||
      flowState === "fetching_ingredients" ||
      flowState === "analyzing_product",
  };
}
