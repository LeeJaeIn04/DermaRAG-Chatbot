import { BookOpen, ChevronDown } from "lucide-react";
import type { IngredientSource } from "../../types/product";

interface IngredientSourcesProps {
  sources: IngredientSource[];
  metadata: Record<string, unknown>;
}

function sourceTitle(source: IngredientSource, index: number) {
  return (
    source.ingredient_kor_name ||
    source.query_ingredient ||
    source.ingredient_eng_name ||
    `성분 근거 ${index + 1}`
  );
}

export function IngredientSources({
  sources,
  metadata,
}: IngredientSourcesProps) {
  return (
    <div className="accordion-stack">
      <details className="source-accordion">
        <summary>
          <span>
            <BookOpen className="size-4" />
            성분 근거 보기
            <small>{sources.length}개 자료</small>
          </span>
          <ChevronDown className="chevron size-4" />
        </summary>
        <div className="source-content">
          {sources.length ? (
            sources.map((source, index) => (
              <article
                className="source-item"
                key={`${source.source || "source"}-${index}`}
              >
                <div className="source-item-head">
                  <strong>{sourceTitle(source, index)}</strong>
                  {typeof source.match_score === "number" && (
                    <span>
                      일치도 {Math.round(source.match_score * 100)}%
                    </span>
                  )}
                </div>
                {source.ingredient_eng_name && (
                  <p className="source-eng">{source.ingredient_eng_name}</p>
                )}
                {source.content && <p>{source.content}</p>}
                <div className="source-meta">
                  {source.cas_no && <span>CAS {source.cas_no}</span>}
                  {source.retrieval_type && (
                    <span>{source.retrieval_type}</span>
                  )}
                  {source.source && <span>{source.source}</span>}
                </div>
              </article>
            ))
          ) : (
            <p className="source-empty">표시할 개별 성분 근거가 없습니다.</p>
          )}
        </div>
      </details>

      {import.meta.env.DEV && (
        <details className="source-accordion developer">
          <summary>
            <span>개발 정보</span>
            <ChevronDown className="chevron size-4" />
          </summary>
          <pre>{JSON.stringify(metadata, null, 2)}</pre>
        </details>
      )}
    </div>
  );
}
