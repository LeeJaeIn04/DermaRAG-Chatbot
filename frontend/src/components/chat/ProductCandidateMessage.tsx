import type { ProductCandidate } from "../../types/product";
import { ProductCard } from "../product/ProductCard";

interface ProductCandidateMessageProps {
  content: string;
  searchQuery: string;
  products: ProductCandidate[];
  selectedProduct: ProductCandidate | null;
  canSelect: boolean;
  onSelect: (
    product: ProductCandidate,
    candidates: ProductCandidate[],
  ) => void;
}

export function ProductCandidateMessage({
  content,
  searchQuery,
  products,
  selectedProduct,
  canSelect,
  onSelect,
}: ProductCandidateMessageProps) {
  return (
    <div className="candidate-message">
      <div className="candidate-heading">
        <span className="step-label">PRODUCT MATCH</span>
        <h2>{content}</h2>
        <p>
          ‘{searchQuery}’ 검색 결과예요. 상품명과 브랜드를 확인해 주세요.
        </p>
      </div>
      <div className="product-grid">
        {products.map((product) => (
          <ProductCard
            key={product.product_id}
            product={product}
            selected={selectedProduct === product}
            disabled={!canSelect}
            onSelect={(selected) => onSelect(selected, products)}
          />
        ))}
      </div>
      {import.meta.env.DEV &&
        selectedProduct &&
        products.includes(selectedProduct) && (
          <details className="selected-product-debug">
            <summary>선택 상품 개발 정보</summary>
            <dl>
              <div>
                <dt>product_id</dt>
                <dd>{selectedProduct.product_id}</dd>
              </div>
              <div>
                <dt>source</dt>
                <dd>{selectedProduct.source}</dd>
              </div>
              <div>
                <dt>product_url</dt>
                <dd>{selectedProduct.product_url}</dd>
              </div>
            </dl>
          </details>
        )}
    </div>
  );
}
