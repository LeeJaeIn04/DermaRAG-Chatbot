from app.products.models import ProductCandidate


class MockProductSearchProvider:
    provider_name = "mock_oliveyoung"

    def search_products(
        self,
        query: str,
        limit: int = 5,
    ) -> list[ProductCandidate]:
        # 실제 올리브영에서 가져오는 것이 아닌 연습용 데이터다.
        products = [
            ProductCandidate(
                product_id="MOCK-SKIN-001",
                source=self.provider_name,
                brand_name="라운드랩",
                product_name="자작나무 수분 선크림 50ml",
                category="unknown",
                category_path=(
                    "스킨케어 > 선케어 > 선크림"
                ),
                product_url=(
                    "https://example.com/products/"
                    "MOCK-SKIN-001"
                ),
                image_url=None,
                original_price=25000,
                sale_price=19900,
                sold_out=False,
                rank=1,
                search_query=query,
            ),
            ProductCandidate(
                product_id="MOCK-COLOR-001",
                source=self.provider_name,
                brand_name="테스트브랜드",
                product_name="글로우 쿠션 15g",
                category="unknown",
                product_url=(
                    "https://example.com/products/"
                    "MOCK-COLOR-001"
                ),
                image_url=None,
                original_price=30000,
                sale_price=24000,
                sold_out=False,
                rank=2,
                search_query=query,
            ),
            ProductCandidate(
                # 올리브영 URL의 goodsNo를 ID로 사용한다.
                product_id="A000000149135",

                # 검색할 때 사용할 상품명
                product_name=(
                    "라운드랩 자작나무 수분 선크림"
                ),

                brand_name="라운드랩",

                # 선크림이므로 현재 분류에서는 skincare로 처리한다.
                category="skincare",
                
                # 실제 전성분 추출에 성공한 올리브영 상품 URL
                product_url=(
                    "https://www.oliveyoung.co.kr/store/goods/"
                    "getGoodsDetail.do?goodsNo=A000000149135"
                ),
            ),
        ]
        return products[:limit]