import { AlertCircle, ChevronDown } from "lucide-react";
import ReactMarkdown from "react-markdown";
import type { ChatMessage as ChatMessageType } from "../../types/chat";
import type {
  ProductCandidate,
  ProductOption,
} from "../../types/product";
import { ProductAnalysisResult } from "../product/ProductAnalysisResult";
import { ProductOptionSelector } from "../product/ProductOptionSelector";
import { ProductCandidateMessage } from "./ProductCandidateMessage";

interface ChatMessageProps {
  message: ChatMessageType;
  selectedProduct: ProductCandidate | null;
  canSelectProduct: boolean;
  onProductSelect: (
    product: ProductCandidate,
    candidates: ProductCandidate[],
  ) => void;
  canSelectOption: boolean;
  onOptionSelect: (
    product: ProductCandidate,
    option: ProductOption,
  ) => void;
}

export function ChatMessage({
  message,
  selectedProduct,
  canSelectProduct,
  onProductSelect,
  canSelectOption,
  onOptionSelect,
}: ChatMessageProps) {
  if (message.kind === "analysis") {
    return (
      <div className="message-row assistant-row analysis-row">
        <div className="assistant-avatar" aria-hidden="true">
          <span>dr</span>
        </div>
        <ProductAnalysisResult analysis={message.analysis} />
      </div>
    );
  }

  if (message.kind === "products") {
    return (
      <div className="message-row assistant-row candidate-row">
        <div className="assistant-avatar" aria-hidden="true">
          <span>dr</span>
        </div>
        <ProductCandidateMessage
          content={message.content}
          searchQuery={message.searchQuery}
          products={message.products}
          selectedProduct={selectedProduct}
          canSelect={canSelectProduct}
          onSelect={onProductSelect}
        />
      </div>
    );
  }

  if (message.kind === "options") {
    return (
      <div className="message-row assistant-row candidate-row">
        <div className="assistant-avatar" aria-hidden="true">
          <span>dr</span>
        </div>
        <ProductOptionSelector
          content={message.content}
          product={message.product}
          options={message.options}
          canSelect={canSelectOption}
          onAnalyze={onOptionSelect}
        />
      </div>
    );
  }

  if (message.kind === "error") {
    return (
      <div className="message-row assistant-row">
        <div className="assistant-avatar error-avatar" aria-hidden="true">
          <AlertCircle className="size-4" />
        </div>
        <div className="error-card" role="alert">
          <strong>{message.content}</strong>
          <p>질문이나 상품을 다시 확인한 뒤 재시도해 주세요.</p>
          {message.detail && (
            <details>
              <summary>
                오류 상세
                <ChevronDown className="size-3.5" />
              </summary>
              <code>{message.detail}</code>
            </details>
          )}
        </div>
      </div>
    );
  }

  const isUser = message.role === "user";
  return (
    <div className={`message-row ${isUser ? "user-row" : "assistant-row"}`}>
      {!isUser && (
        <div className="assistant-avatar" aria-hidden="true">
          <span>dr</span>
        </div>
      )}
      <div className={isUser ? "user-bubble" : "assistant-bubble"}>
        <ReactMarkdown>{message.content}</ReactMarkdown>
      </div>
    </div>
  );
}
