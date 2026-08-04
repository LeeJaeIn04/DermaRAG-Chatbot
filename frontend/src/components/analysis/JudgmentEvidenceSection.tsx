import { BookOpenCheck } from "lucide-react";
import type {
  ProductFragranceAllergenSource,
  ProductRegulationSource,
} from "../../types/product";
import { AllergenSection } from "./AllergenSection";
import { RegulationSection } from "./RegulationSection";

interface JudgmentEvidenceSectionProps {
  regulationCount: number;
  regulations: ProductRegulationSource[];
  allergenCount: number;
  allergens: ProductFragranceAllergenSource[];
}

export function JudgmentEvidenceSection({
  regulationCount,
  regulations,
  allergenCount,
  allergens,
}: JudgmentEvidenceSectionProps) {
  return (
    <section className="analysis-section evidence-section">
      <div className="section-heading">
        <span className="section-icon sage">
          <BookOpenCheck className="size-5" />
        </span>
        <div>
          <h3>판정 근거 및 출처</h3>
          <p>제품 전성분과 식약처 고시 자료를 대조한 결과예요.</p>
        </div>
        <span className="count-pill">
          {regulationCount + allergenCount}건
        </span>
      </div>

      <div className="evidence-groups">
        <RegulationSection
          count={regulationCount}
          regulations={regulations}
        />
        <AllergenSection count={allergenCount} allergens={allergens} />
      </div>
    </section>
  );
}
