import { Ban, FileCheck2, Scale } from "lucide-react";
import type { ProductRegulationSource } from "../../types/product";

interface RegulationSectionProps {
  count: number;
  regulations: ProductRegulationSource[];
}

const categoryLabels: Record<ProductRegulationSource["category"], string> = {
  prohibited: "사용 금지",
  preservative: "보존제",
  uv_filter: "자외선 차단 성분",
  hair_dye: "염모 성분",
  restricted_other: "기타 사용 제한",
};

const matchTypeLabels: Record<
  ProductRegulationSource["match_type"],
  string
> = {
  ingredient_kor_name: "한글 성분명",
  chemical_name: "화학명",
  cas_no: "CAS 번호",
};

function Field({
  label,
  value,
}: {
  label: string;
  value?: string | null;
}) {
  if (!value) return null;
  return (
    <div className="result-field">
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

export function RegulationSection({
  count,
  regulations,
}: RegulationSectionProps) {
  return (
    <section className="evidence-group">
      <div className="evidence-group-heading">
        <span className="evidence-group-icon sage">
          <Scale className="size-5" />
        </span>
        <div>
          <h4>식약처 규제 정보</h4>
          <p>제품 전성분과 정확히 일치한 사용 기준을 확인했어요.</p>
        </div>
        <span className="count-pill">{count}건</span>
      </div>

      {regulations.length ? (
        <div className="result-list">
          {regulations.map((item, index) => {
            const prohibited = item.regulation_type === "prohibited";
            return (
              <article
                className="evidence-card"
                key={`${item.query_ingredient}-${index}`}
              >
                <div className="evidence-card-head">
                  <div>
                    <p className="matched-label">전성분 표기</p>
                    <h4>{item.query_ingredient}</h4>
                    {item.matched_name !== item.query_ingredient && (
                      <p className="matched-name">
                        식약처 명칭 · {item.matched_name}
                      </p>
                    )}
                  </div>
                  <span
                    className={`status-badge ${prohibited ? "prohibited" : "conditional"}`}
                  >
                    {prohibited ? (
                      <Ban className="size-3.5" />
                    ) : (
                      <FileCheck2 className="size-3.5" />
                    )}
                    {prohibited ? "사용 금지" : "사용 조건 있음"}
                  </span>
                </div>
                <dl className="result-field-grid">
                  <Field
                    label="판정 근거"
                    value={`${matchTypeLabels[item.match_type]} 일치`}
                  />
                  <Field label="분류" value={categoryLabels[item.category]} />
                  <Field label="화학명" value={item.chemical_name} />
                  <Field label="CAS 번호" value={item.cas_no} />
                  <Field label="사용 한도" value={item.max_concentration} />
                  <Field label="적용 제품" value={item.product_scope} />
                  <Field label="사용 조건" value={item.use_conditions} />
                  <Field label="주의 문구" value={item.warning_text} />
                </dl>
                <p className="source-line">
                  <strong>출처</strong>
                  {` · ${item.source_authority} · ${item.source_document}`}
                  {item.notice_label
                    ? ` · ${item.notice_label}`
                    : item.notice_number
                      ? ` · ${item.notice_number}`
                      : ""}
                  {item.notice_date ? ` (${item.notice_date})` : ""}
                  {item.source_section ? ` · ${item.source_section}` : ""}
                  {item.source_table ? ` · 표 ${item.source_table}` : ""}
                </p>
              </article>
            );
          })}
        </div>
      ) : (
        <div className="calm-empty">
          <FileCheck2 className="size-5" />
          <p>
            현재 식약처 규제 목록과 정확히 일치한 성분이 없습니다.
          </p>
        </div>
      )}
    </section>
  );
}
