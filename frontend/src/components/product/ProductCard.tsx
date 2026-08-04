import { Check, ImageOff } from "lucide-react";
import { useState } from "react";
import type { ProductCandidate } from "../../types/product";
import { getProductAnalysisEligibility } from "../../utils/products";

interface ProductCardProps {
  product: ProductCandidate;
  onSelect: (product: ProductCandidate) => void;
  selected: boolean;
  disabled: boolean;
}

const currency = new Intl.NumberFormat("ko-KR");

export function ProductCard({
  product,
  onSelect,
  selected,
  disabled,
}: ProductCardProps) {
  const [imageFailed, setImageFailed] = useState(false);
  const hasImage = Boolean(product.image_url) && !imageFailed;
  const eligibility = getProductAnalysisEligibility(product);
  const selectionDisabled = disabled || !eligibility.canAnalyze;
  const hasDiscount =
    product.sale_price !== null &&
    product.original_price !== null &&
    product.sale_price < product.original_price;
  const discountRate = hasDiscount
    ? Math.round(
        ((product.original_price! - product.sale_price!) /
          product.original_price!) *
          100,
      )
    : null;

  return (
    <article className={`product-card ${selected ? "is-selected" : ""}`}>
      <div className="product-image-wrap">
        {hasImage ? (
          <img
            src={product.image_url!}
            alt={`${product.product_name} 상품 이미지`}
            className="product-image"
            loading="lazy"
            onError={() => setImageFailed(true)}
          />
        ) : (
          <div className="product-placeholder" role="img" aria-label="이미지 없음">
            <div className="placeholder-glow" />
            <ImageOff className="size-7" strokeWidth={1.4} />
            <span>DermaRAG</span>
          </div>
        )}
        {product.rank && (
          <span className="rank-badge">추천 {product.rank}</span>
        )}
      </div>

      <div className="product-body">
        <div>
          <p className="product-brand">
            {product.brand_name || "브랜드 정보 없음"}
          </p>
          <h3 className="product-name">{product.product_name}</h3>
          {!eligibility.canAnalyze && (
            <p className="product-unavailable">{eligibility.reason}</p>
          )}
        </div>

        <div className="product-footer">
          <div className="price-block">
            {hasDiscount && (
              <span className="original-price">
                {currency.format(product.original_price!)}원
              </span>
            )}
            <div>
              {discountRate !== null && (
                <span className="discount-rate">{discountRate}%</span>
              )}
              <strong>
                {product.sale_price !== null
                  ? `${currency.format(product.sale_price)}원`
                  : product.original_price !== null
                    ? `${currency.format(product.original_price)}원`
                    : "가격 정보 없음"}
              </strong>
            </div>
          </div>
          <button
            type="button"
            className="select-product-button"
            onClick={() => onSelect(product)}
            disabled={selectionDisabled}
            aria-label={`${product.product_name} 분석`}
            title={eligibility.reason || undefined}
          >
            {selected ? (
              <>
                <Check className="size-4" /> 선택됨
              </>
            ) : (
              "이 상품 선택"
            )}
          </button>
        </div>
      </div>
    </article>
  );
}
