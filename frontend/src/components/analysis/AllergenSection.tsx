import { Info, Sparkles } from "lucide-react";
import type { ProductFragranceAllergenSource } from "../../types/product";

interface AllergenSectionProps {
  count: number;
  allergens: ProductFragranceAllergenSource[];
}

const matchTypeLabels: Record<
  ProductFragranceAllergenSource["match_type"],
  string
> = {
  ingredient_kor_name: "한글 성분명",
  ingredient_eng_name: "영문 성분명",
  inci_name: "INCI 명칭",
  alias: "동의어",
  cas_no: "CAS 번호",
};

export function AllergenSection({
  count,
  allergens,
}: AllergenSectionProps) {
  return (
    <section className="evidence-group">
      <div className="evidence-group-heading">
        <span className="evidence-group-icon sand">
          <Sparkles className="size-5" />
        </span>
        <div>
          <h4>향료 알레르기 표시 대상</h4>
          <p>법적 표시 대상 목록과 전성분을 대조한 결과예요.</p>
        </div>
        <span className="count-pill">{count}건</span>
      </div>

      <div className="allergen-notice">
        <Info className="mt-0.5 size-4 shrink-0" />
        <p>
          향료 알레르기 표시 대상이라는 사실만으로 모든 사용자에게
          알레르기 반응을 일으킨다는 뜻은 아닙니다. 전성분표만으로 실제
          함량이 표시 기준을 초과하는지 판단할 수 없습니다.
        </p>
      </div>

      {allergens.length ? (
        <div className="result-list">
          {allergens.map((item, index) => (
            <article
              className="evidence-card allergen-card"
              key={`${item.query_ingredient}-${index}`}
            >
              <div className="evidence-card-head">
                <div>
                  <p className="matched-label">전성분 표기</p>
                  <h4>{item.query_ingredient}</h4>
                  <p className="matched-name">
                    {item.ingredient_kor_name}
                    {item.ingredient_eng_name
                      ? ` · ${item.ingredient_eng_name}`
                      : ""}
                  </p>
                </div>
                <span className="status-badge allergen">
                  표시 대상
                </span>
              </div>
              <dl className="result-field-grid">
                <div className="result-field">
                  <dt>판정 근거</dt>
                  <dd>{matchTypeLabels[item.match_type]} 일치</dd>
                </div>
                {item.cas_numbers.length > 0 && (
                  <div className="result-field">
                    <dt>CAS 번호</dt>
                    <dd>{item.cas_numbers.join(", ")}</dd>
                  </div>
                )}
                <div className="result-field">
                  <dt>법적 상태</dt>
                  <dd>{item.legal_status}</dd>
                </div>
                <div className="result-field">
                  <dt>적용 범위</dt>
                  <dd>
                    {[item.jurisdiction, item.evidence_scope]
                      .filter(Boolean)
                      .join(" · ")}
                  </dd>
                </div>
                {item.rinse_off_threshold && (
                  <div className="result-field">
                    <dt>씻어내는 제품 기준</dt>
                    <dd>{item.rinse_off_threshold}</dd>
                  </div>
                )}
                {item.leave_on_threshold && (
                  <div className="result-field">
                    <dt>사용 후 씻지 않는 제품 기준</dt>
                    <dd>{item.leave_on_threshold}</dd>
                  </div>
                )}
              </dl>
              <p className="source-line">
                <strong>출처</strong>
                {` · ${item.source_authority} · ${item.source_document}`}
                {item.source_document_version
                  ? ` · ${item.source_document_version}`
                  : ""}
                {item.source_document_date
                  ? ` (${item.source_document_date})`
                  : ""}
                {item.source_section ? ` · ${item.source_section}` : ""}
                {item.source_page ? ` · ${item.source_page}쪽` : ""}
              </p>
            </article>
          ))}
        </div>
      ) : (
        <div className="calm-empty">
          <Sparkles className="size-5" />
          <p>
            현재 식약처 향료 알레르기 표시 대상 목록과 정확히 일치한
            성분이 없습니다.
          </p>
        </div>
      )}
    </section>
  );
}
