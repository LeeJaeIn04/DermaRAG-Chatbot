import {
  CheckCircle2,
  Database,
  Droplets,
  Leaf,
  PackageCheck,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import type { ProductAnalysisResponse } from "../../types/product";
import { ActionTips } from "../analysis/ActionTips";
import { IngredientSources } from "../analysis/IngredientSources";
import { JudgmentEvidenceSection } from "../analysis/JudgmentEvidenceSection";
import { SkinCompatibilitySection } from "../analysis/SkinCompatibilitySection";

interface ProductAnalysisResultProps {
  analysis: ProductAnalysisResponse;
}

export function ProductAnalysisResult({
  analysis,
}: ProductAnalysisResultProps) {
  return (
    <div className="analysis-result">
      <header className="analysis-hero">
        <div className="analysis-product-icon" aria-hidden="true">
          <Leaf className="size-6" />
        </div>
        <div className="analysis-product-copy">
          <span className="complete-label">
            <CheckCircle2 className="size-3.5" />
            ANALYSIS COMPLETE
          </span>
          <p>{analysis.product.brand_name || "선택한 제품"}</p>
          <h2>{analysis.product.product_name}</h2>
          {analysis.option_specific_ingredients &&
            analysis.selected_option_name && (
              <span className="analysis-option-name">
                선택 옵션 · {analysis.selected_option_name}
              </span>
            )}
        </div>
        <div className="analysis-stats" aria-label="분석 요약">
          <div>
            <strong>{analysis.ingredient_count}</strong>
            <span>전성분</span>
          </div>
          <div>
            <strong>{analysis.regulation_count}</strong>
            <span>규제 정보</span>
          </div>
          <div>
            <strong>{analysis.allergen_count}</strong>
            <span>표시 대상</span>
          </div>
        </div>
      </header>

      <section className="answer-card">
        <div className="answer-heading">
          <span>
            <Droplets className="size-5" />
          </span>
          <div>
            <p>PERSONALIZED SUMMARY</p>
            <h3>종합 분석</h3>
          </div>
        </div>
        <div className="markdown-answer">
          <ReactMarkdown>{analysis.answer}</ReactMarkdown>
        </div>
        <div className="analysis-cache-note">
          {analysis.cache_hit ? (
            <Database className="size-4" />
          ) : (
            <PackageCheck className="size-4" />
          )}
          <span>
            {analysis.cache_hit
              ? "저장된 최신 전성분 정보를 사용했어요."
              : analysis.extraction_performed
                ? "상품 페이지에서 전성분을 새로 확인했어요."
                : "확인된 전성분 정보를 사용했어요."}
          </span>
        </div>
      </section>

      <SkinCompatibilitySection
        notices={analysis.skin_compatibility || []}
      />
      <JudgmentEvidenceSection
        regulationCount={analysis.regulation_count}
        regulations={analysis.regulations || []}
        allergenCount={analysis.allergen_count}
        allergens={analysis.allergens || []}
      />
      <IngredientSources
        sources={analysis.sources}
        metadata={analysis.metadata}
      />
      <ActionTips />
    </div>
  );
}
