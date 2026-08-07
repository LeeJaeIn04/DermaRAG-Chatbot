import { Check, ImageOff, Sparkles } from "lucide-react";
import { useState } from "react";
import type {
  ProductCandidate,
  ProductOption,
} from "../../types/product";
import {
  isOptionAnalyzable,
  selectDefaultAnalyzableOption,
} from "../../utils/products";

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
  // 기본 선택은 목록의 첫 옵션이 아니라 첫 번째 분석 가능(ready)
  // 옵션이다. 분석 가능한 옵션이 없으면 선택 없음으로 시작한다.
  const [selectedKey, setSelectedKey] = useState<string | null>(
    () => selectDefaultAnalyzableOption(options)?.internal_option_key ?? null,
  );
  const selectedOption =
    options.find(
      (option) => option.internal_option_key === selectedKey,
    ) || null;
  const analyzableCount = options.filter(isOptionAnalyzable).length;

  return (
    <section className="option-selector-card">
      <header>
        <p>{content}</p>
        <span>{analyzableCount}개 옵션 분석 가능</span>
      </header>

      <div className="option-grid" role="listbox" aria-label="상품 옵션">
        {options.map((option) => {
          const selected =
            option.internal_option_key === selectedKey;
          const available = isOptionAnalyzable(option);

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
                {available ? "분석 가능" : "분석 불가"}
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
