import {
  ExternalLink,
  HeartPulse,
  Info,
} from "lucide-react";
import type {
  SkinCompatibilityNotice,
} from "../../types/chat";
import { sortSkinCompatibilityNotices } from "../../utils/skin";

const levelLabels: Record<
  SkinCompatibilityNotice["level"],
  string
> = {
  high: "주의 우선순위 높음",
  caution: "주의 가능성 있음",
  reference: "사용 시 참고",
  beneficial: "도움이 될 가능성 있음",
};

interface SkinCompatibilitySectionProps {
  notices: SkinCompatibilityNotice[];
}

export function SkinCompatibilitySection({
  notices,
}: SkinCompatibilitySectionProps) {
  const sortedNotices = sortSkinCompatibilityNotices(notices);

  return (
    <section className="analysis-section compatibility-section">
      <div className="section-heading">
        <span className="section-icon rose">
          <HeartPulse className="size-5" />
        </span>
        <div>
          <h3>내 피부 정보와 성분 비교</h3>
          <p>입력한 피부 상태와 규칙 기반 성분 정보를 비교했어요.</p>
        </div>
        <span className="count-pill">{notices.length}건</span>
      </div>

      <div className="compatibility-notice">
        <Info className="mt-0.5 size-4 shrink-0" />
        <p>
          성분표만으로 실제 반응을 확정할 수 없습니다. 피부 상태,
          함량과 완제품 제형에 따라 반응이 달라질 수 있습니다.
        </p>
      </div>

      {sortedNotices.length ? (
        <div className="result-list">
          {sortedNotices.map((notice, index) => (
            <article
              className={`compatibility-card level-${notice.level}`}
              key={`${notice.rule_id}-${notice.ingredient_name}-${index}`}
            >
              <div className="compatibility-card-head">
                <div>
                  <p className="matched-label">전성분 표기</p>
                  <h4>{notice.ingredient_name}</h4>
                  <p className="matched-name">{notice.category}</p>
                </div>
                <span className={`compatibility-badge ${notice.level}`}>
                  {levelLabels[notice.level]}
                </span>
              </div>

              <p className="compatibility-reason">{notice.reason}</p>
              {notice.condition && (
                <p className="compatibility-condition">
                  조건 · {notice.condition}
                </p>
              )}

              {(notice.possible_concerns.length > 0 ||
                notice.evidence_level ||
                notice.source_urls.length > 0) && (
                <details className="compatibility-details">
                  <summary>근거와 참고 정보</summary>
                  {notice.possible_concerns.length > 0 && (
                    <p>
                      참고 요소 · {notice.possible_concerns.join(", ")}
                    </p>
                  )}
                  {notice.evidence_level && (
                    <p>근거 수준 · {notice.evidence_level}</p>
                  )}
                  {notice.source_urls.length > 0 && (
                    <div className="compatibility-sources">
                      {notice.source_urls.map((url, sourceIndex) => (
                        <a
                          href={url}
                          target="_blank"
                          rel="noreferrer"
                          key={`${url}-${sourceIndex}`}
                        >
                          {notice.source_titles[sourceIndex] ||
                            `출처 ${sourceIndex + 1}`}
                          <ExternalLink className="size-3" />
                        </a>
                      ))}
                    </div>
                  )}
                </details>
              )}
            </article>
          ))}
        </div>
      ) : (
        <div className="calm-empty">
          <HeartPulse className="size-5" />
          <p>
            현재 입력한 피부 정보와 직접 매칭되는 성분 규칙은 확인되지
            않았습니다. 이는 제품이 안전하다는 의미가 아닙니다.
          </p>
        </div>
      )}
    </section>
  );
}
