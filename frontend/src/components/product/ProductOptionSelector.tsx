import { Check, ImageOff, Sparkles } from "lucide-react";
import { useState } from "react";
import type {
  ProductCandidate,
  ProductOption,
} from "../../types/product";

interface ProductOptionSelectorProps {
  content: string;
  product: ProductCandidate;
  options: ProductOption[];
  canSelect: boolean;
  onAnalyze: (
    product: ProductCandidate,
    option: ProductOption,
  ) => void;
}

export function ProductOptionSelector({
  content,
  product,
  options,
  canSelect,
  onAnalyze,
}: ProductOptionSelectorProps) {
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const selectedOption =
    options.find(
      (option) => option.internal_option_key === selectedKey,
    ) || null;

  return (
    <section className="option-selector-card">
      <header>
        <p>{content}</p>
        <span>{options.length}개 옵션 분석 가능</span>
      </header>

      <div className="option-grid" role="listbox" aria-label="상품 옵션">
        {options.map((option) => {
          const selected =
            option.internal_option_key === selectedKey;
          const available = option.mapping_status === "matched";

          return (
            <button
              type="button"
              role="option"
              aria-selected={selected}
              className={`option-card ${selected ? "is-selected" : ""}`}
              key={option.internal_option_key}
              disabled={!canSelect || !available}
              onClick={() =>
                setSelectedKey(option.internal_option_key)
              }
            >
              <span className="option-image">
                {option.image_url ? (
                  <img src={option.image_url} alt="" />
                ) : (
                  <ImageOff className="size-4" />
                )}
              </span>
              <span className="option-name">{option.option_name}</span>
              <span className="option-availability">
                {available ? "분석 가능" : "전성분 매칭 불가"}
              </span>
              {selected && (
                <i aria-hidden="true">
                  <Check className="size-3.5" />
                </i>
              )}
            </button>
          );
        })}
      </div>

      <button
        type="button"
        className="analyze-option-button"
        disabled={!canSelect || !selectedOption}
        onClick={() => {
          if (selectedOption) onAnalyze(product, selectedOption);
        }}
      >
        <Sparkles className="size-4" />
        이 옵션 선택
      </button>
    </section>
  );
}
