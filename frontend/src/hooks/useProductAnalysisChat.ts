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
  SkinProfile,
} from "../types/chat";
import type {
  ProductAnalysisRequest,
  ProductCandidate,
  ProductOption,
} from "../types/product";
import { removeAnalysisMessages } from "../utils/chat";
import {
  acquireAnalysisLock,
  assembleProductAnalysisRequest,
  createAnalysisAttempt,
  createPendingAnalysisTarget,
  getBackFlowState,
  releaseAnalysisLock,
} from "../utils/analysisFlow";
import type {
  AnalysisAttempt,
  PendingAnalysisTarget,
} from "../utils/analysisFlow";
import {
  createProductSearchQuery,
  getProductAnalysisEligibility,
  isOptionAnalyzable,
} from "../utils/products";
import {
  buildSkinAnalysisFields,
  getSkinPreferenceDecision,
  hasSkinProfileData,
} from "../utils/skin";

const initialAssistantMessage: ChatMessage = {
  id: "welcome",
  role: "assistant",
  kind: "text",
  content:
    "안녕하세요. **DermaRAG**입니다.\n\n궁금한 화장품이나 피부 반응을 입력해 주세요.",
  createdAt: new Date(),
};

let idCounter = 0;

function createId(prefix: string) {
  if (typeof crypto.randomUUID === "function") {
    return `${prefix}-${crypto.randomUUID()}`;
  }

  idCounter += 1;
  return `${prefix}-${Date.now().toString(36)}-${idCounter.toString(36)}`;
}

export function buildProductAnalysisRequest(
  product: ProductCandidate,
  question: string,
  profile: SkinProfile | null,
  option?: {
    optionId?: string;
    optionName?: string | null;
    sourceOptionId?: string | null;
  },
  settings: { useSkinProfile?: boolean } = {},
): ProductAnalysisRequest {
  const eligibility = getProductAnalysisEligibility(product);
  if (!eligibility.canAnalyze) {
    throw new ApiError(
      eligibility.reason || "선택한 상품의 올리브영 주소를 확인할 수 없어요.",
      400,
      `product_id=${product.product_id}, source=${product.source}, product_url=${product.product_url}`,
    );
  }

  const skinFields = buildSkinAnalysisFields(
    profile,
    settings.useSkinProfile !== false,
  );

  // 검색 결과의 ProductCandidate 참조와 모든 필드를 그대로 유지한다.
  return assembleProductAnalysisRequest(product, question, skinFields, option);
}

export function useProductAnalysisChat(
  profile: SkinProfile,
  onRequestSkinProfile?: () => void,
) {
  const [messages, setMessages] = useState<ChatMessage[]>([
    initialAssistantMessage,
  ]);
  const [flowState, setFlowState] = useState<ChatFlowState>("idle");
  const [currentQuestion, setCurrentQuestion] = useState("");
  const [selectedProduct, setSelectedProduct] =
    useState<ProductCandidate | null>(null);
  const [selectedOption, setSelectedOption] =
    useState<ProductOption | null>(null);
  const [pendingAnalysisTarget, setPendingAnalysisTarget] =
    useState<PendingAnalysisTarget | null>(null);
  const [activeSkinPreferenceMessageId, setActiveSkinPreferenceMessageId] =
    useState<string | null>(null);
  const [retryMessageId, setRetryMessageId] = useState<string | null>(null);
  const busyRef = useRef(false);
  const skinDecisionRef = useRef(false);
  const retryAttemptRef = useRef<AnalysisAttempt | null>(null);

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
      const errorMessageId = createId("error");

      setFlowState("error");
      setRetryMessageId(errorMessageId);
      clearAnalysisMessages();
      appendMessage({
        id: errorMessageId,
        role: "assistant",
        kind: "error",
        content: apiError.message,
        detail: apiError.detail,
        createdAt: new Date(),
      });
    },
    [appendMessage, clearAnalysisMessages],
  );

  const resetPendingAnalysis = useCallback(() => {
    setPendingAnalysisTarget(null);
    setActiveSkinPreferenceMessageId(null);
    setRetryMessageId(null);
    skinDecisionRef.current = false;
    retryAttemptRef.current = null;
  }, []);

  const submitQuestion = useCallback(
    async (question: string) => {
      const normalizedQuestion = question.trim();
      if (!normalizedQuestion || !acquireAnalysisLock(busyRef)) return;

      clearAnalysisMessages();
      resetPendingAnalysis();
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
        releaseAnalysisLock(busyRef);
      }
    },
    [appendMessage, clearAnalysisMessages, reportError, resetPendingAnalysis],
  );

  const prepareAnalysis = useCallback(
    (product: ProductCandidate, option: ProductOption | null = null) => {
      const target = createPendingAnalysisTarget(product, option);
      const promptMessageId = createId("skin-preference");

      setPendingAnalysisTarget(target);
      setActiveSkinPreferenceMessageId(promptMessageId);
      setRetryMessageId(null);
      skinDecisionRef.current = false;
      retryAttemptRef.current = null;
      appendMessage({
        id: promptMessageId,
        role: "assistant",
        kind: "skin-preference",
        content: "피부 정보도 반영해서 분석할까요?",
        productName: `${product.brand_name ? `${product.brand_name} ` : ""}${product.product_name}`,
        optionName: option?.option_name || null,
        createdAt: new Date(),
      });
      setFlowState("waiting_for_skin_preference");
    },
    [appendMessage],
  );

  const runAnalysis = useCallback(
    async (
      attempt: AnalysisAttempt,
      { announceChoice = true }: { announceChoice?: boolean } = {},
    ) => {
      if (!acquireAnalysisLock(busyRef)) return false;

      const stableAttempt = createAnalysisAttempt(
        attempt.target,
        attempt.useSkinProfile,
        attempt.profile,
      );
      retryAttemptRef.current = stableAttempt;
      setRetryMessageId(null);
      setActiveSkinPreferenceMessageId(null);
      setFlowState("fetching_ingredients");

      if (announceChoice) {
        appendMessage({
          id: createId("skin-choice"),
          role: "user",
          kind: "text",
          content: attempt.useSkinProfile
            ? "저장한 피부 정보를 반영해서 분석해 주세요."
            : "피부 정보 없이 기본 분석을 진행해 주세요.",
          createdAt: new Date(),
        });
      }

      let analysisTimer: number | undefined;
      try {
        analysisTimer = window.setTimeout(() => {
          setFlowState("analyzing_product");
        }, 900);

        const { product, option } = stableAttempt.target;
        const analysisRequest = buildProductAnalysisRequest(
          product,
          currentQuestion,
          stableAttempt.profile,
          option
            ? {
                optionId: option.internal_option_key,
                optionName: option.option_name,
                sourceOptionId: option.source_option_id,
              }
            : undefined,
          { useSkinProfile: stableAttempt.useSkinProfile },
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
        setPendingAnalysisTarget(null);
        retryAttemptRef.current = null;
        skinDecisionRef.current = false;
        return true;
      } catch (error) {
        if (analysisTimer) window.clearTimeout(analysisTimer);
        reportError(error);
        return false;
      } finally {
        releaseAnalysisLock(busyRef);
      }
    },
    [appendMessage, currentQuestion, reportError],
  );

  const chooseProduct = useCallback(
    async (product: ProductCandidate, candidates: ProductCandidate[]) => {
      if (
        flowState !== "waiting_for_product_selection" ||
        !acquireAnalysisLock(busyRef)
      ) {
        return;
      }

      const eligibility = getProductAnalysisEligibility(product);
      if (!eligibility.canAnalyze) {
        releaseAnalysisLock(busyRef);
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

      clearAnalysisMessages();
      resetPendingAnalysis();
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
        content: `${product.brand_name ? `${product.brand_name} ` : ""}${product.product_name}을(를) 선택했어요.`,
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
              "현재 이 상품의 옵션별 전성분 정보를 정확히 확인할 수 없습니다. 다른 상품을 선택해 주세요.",
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

        prepareAnalysis(product);
      } catch (error) {
        reportError(error);
      } finally {
        releaseAnalysisLock(busyRef);
      }
    },
    [
      appendMessage,
      clearAnalysisMessages,
      flowState,
      prepareAnalysis,
      reportError,
      resetPendingAnalysis,
    ],
  );

  const chooseOption = useCallback(
    (product: ProductCandidate, option: ProductOption) => {
      if (
        flowState !== "waiting_for_option_selection" ||
        !isOptionAnalyzable(option) ||
        !acquireAnalysisLock(busyRef)
      ) {
        return;
      }

      try {
        clearAnalysisMessages();
        resetPendingAnalysis();
        setSelectedOption(option);
        appendMessage({
          id: createId("option-selection"),
          role: "user",
          kind: "text",
          content: `${option.option_name} 옵션을 선택했어요.`,
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

        prepareAnalysis(product, option);
      } finally {
        releaseAnalysisLock(busyRef);
      }
    },
    [
      appendMessage,
      clearAnalysisMessages,
      flowState,
      prepareAnalysis,
      resetPendingAnalysis,
    ],
  );

  const useSkinProfileForPendingAnalysis = useCallback(() => {
    if (
      flowState !== "waiting_for_skin_preference" ||
      !pendingAnalysisTarget ||
      busyRef.current ||
      skinDecisionRef.current
    ) {
      return;
    }

    skinDecisionRef.current = true;
    if (getSkinPreferenceDecision(profile) === "collect_profile") {
      setFlowState("waiting_for_skin_profile");
      onRequestSkinProfile?.();
      return;
    }

    void runAnalysis({
      target: pendingAnalysisTarget,
      useSkinProfile: true,
      profile,
    });
  }, [
    flowState,
    onRequestSkinProfile,
    pendingAnalysisTarget,
    profile,
    runAnalysis,
  ]);

  const skipSkinProfileForPendingAnalysis = useCallback(() => {
    if (
      flowState !== "waiting_for_skin_preference" ||
      !pendingAnalysisTarget ||
      busyRef.current ||
      skinDecisionRef.current
    ) {
      return;
    }

    skinDecisionRef.current = true;
    void runAnalysis({
      target: pendingAnalysisTarget,
      useSkinProfile: false,
      profile: null,
    });
  }, [flowState, pendingAnalysisTarget, runAnalysis]);

  const completeSkinProfileForPendingAnalysis = useCallback(
    (savedProfile: SkinProfile) => {
      if (
        flowState !== "waiting_for_skin_profile" ||
        !pendingAnalysisTarget ||
        busyRef.current ||
        !hasSkinProfileData(savedProfile)
      ) {
        return;
      }

      void runAnalysis({
        target: pendingAnalysisTarget,
        useSkinProfile: true,
        profile: savedProfile,
      });
    },
    [flowState, pendingAnalysisTarget, runAnalysis],
  );

  const cancelSkinProfileEntry = useCallback(() => {
    if (flowState !== "waiting_for_skin_profile" || busyRef.current) return;
    skinDecisionRef.current = false;
    setFlowState("waiting_for_skin_preference");
  }, [flowState]);

  const goBackFromSkinPreference = useCallback(() => {
    if (
      flowState !== "waiting_for_skin_preference" ||
      !pendingAnalysisTarget ||
      busyRef.current ||
      skinDecisionRef.current
    ) {
      return;
    }

    const backState = getBackFlowState(pendingAnalysisTarget);
    if (pendingAnalysisTarget.option) {
      setSelectedOption(null);
    } else {
      setSelectedProduct(null);
    }
    resetPendingAnalysis();
    setFlowState(backState);
  }, [flowState, pendingAnalysisTarget, resetPendingAnalysis]);

  const retryAnalysis = useCallback(() => {
    if (flowState !== "error" || !retryAttemptRef.current || busyRef.current) {
      return;
    }
    void runAnalysis(retryAttemptRef.current, { announceChoice: false });
  }, [flowState, runAnalysis]);

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
    resetPendingAnalysis();
  }, [resetPendingAnalysis]);

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
    pendingAnalysisTarget,
    activeSkinPreferenceMessageId,
    retryMessageId,
    canRetryAnalysis:
      flowState === "error" && pendingAnalysisTarget !== null,
    recentAnalyses,
    submitQuestion,
    chooseProduct,
    chooseOption,
    useSkinProfileForPendingAnalysis,
    skipSkinProfileForPendingAnalysis,
    completeSkinProfileForPendingAnalysis,
    cancelSkinProfileEntry,
    goBackFromSkinPreference,
    retryAnalysis,
    startNewChat,
    isBusy:
      flowState === "classifying_intent" ||
      flowState === "searching_products" ||
      flowState === "fetching_ingredients" ||
      flowState === "analyzing_product",
  };
}
