class ProductDataUnavailableError(RuntimeError):
    """완전한 사전 수집 데이터가 없고 실시간 수집도 금지된 경우."""

    code = "PRODUCT_NOT_PREFETCHED"
    public_message = (
        "이 상품은 아직 분석 데이터가 준비되지 않았습니다. "
        "다른 상품을 선택하거나 데이터가 준비된 후 다시 시도해 주세요."
    )

    def __init__(self) -> None:
        super().__init__(self.public_message)


class ProductCollectionRetryLaterError(RuntimeError):
    code = "PRODUCT_COLLECTION_RETRY_LATER"
    public_message = (
        "상품 정보를 다시 확인 중입니다. 잠시 후 다시 시도해 주세요."
    )

    def __init__(self) -> None:
        super().__init__(self.public_message)
