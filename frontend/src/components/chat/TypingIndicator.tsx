import { LoaderCircle, Search, Sparkles } from "lucide-react";
import type { ChatFlowState } from "../../types/chat";

const labels: Partial<Record<ChatFlowState, string>> = {
  classifying_intent: "질문을 이해하고 있어요",
  searching_products: "상품을 검색하고 있어요",
  fetching_ingredients: "상품 전성분을 확인하고 있어요",
  analyzing_product: "식약처 성분·규제·알레르겐 정보를 분석하고 있어요",
};

interface TypingIndicatorProps {
  state: ChatFlowState;
}

export function TypingIndicator({ state }: TypingIndicatorProps) {
  const label = labels[state];
  if (!label) return null;

  const Icon =
    state === "searching_products"
      ? Search
      : state === "analyzing_product"
        ? Sparkles
        : LoaderCircle;

  return (
    <div className="message-row assistant-row" aria-live="polite">
      <div className="assistant-avatar" aria-hidden="true">
        <span>dr</span>
      </div>
      <div className="typing-card">
        <Icon className="size-4 animate-spin text-teal-700" />
        <span>{label}</span>
        <span className="typing-dots" aria-hidden="true">
          <i />
          <i />
          <i />
        </span>
      </div>
    </div>
  );
}
