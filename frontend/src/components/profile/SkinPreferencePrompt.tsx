import { ArrowLeft, Sparkles, UserRound, WandSparkles } from "lucide-react";

interface SkinPreferencePromptProps {
  content: string;
  productName: string;
  optionName: string | null;
  profileSummary: string[];
  canChoose: boolean;
  onUseProfile: () => void;
  onSkip: () => void;
  onBack: () => void;
}

export function SkinPreferencePrompt({
  content,
  productName,
  optionName,
  profileSummary,
  canChoose,
  onUseProfile,
  onSkip,
  onBack,
}: SkinPreferencePromptProps) {
  const hasSavedProfile = profileSummary.length > 0;

  return (
    <section className="skin-preference-card">
      <header>
        <span className="skin-preference-icon" aria-hidden="true">
          <UserRound className="size-5" />
        </span>
        <div>
          <span className="step-label">PERSONALIZE</span>
          <h2>{content}</h2>
          <p>
            피부 타입과 고민을 함께 반영하면 성분 적합성을 더 자세히
            확인할 수 있어요.
          </p>
        </div>
      </header>

      <div className="skin-preference-target">
        <strong>{productName}</strong>
        {optionName && <span>{optionName}</span>}
      </div>

      {hasSavedProfile && (
        <div className="skin-profile-summary" aria-label="저장된 피부 정보">
          <span>현재 저장된 정보</span>
          <div>
            {profileSummary.map((item) => (
              <i key={item}>{item}</i>
            ))}
          </div>
        </div>
      )}

      <p className="skin-preference-note">
        입력하지 않아도 규제·알레르겐·일반 성분 분석은 진행됩니다.
      </p>

      <div className="skin-preference-actions">
        <button
          type="button"
          className="skin-profile-action"
          disabled={!canChoose}
          onClick={onUseProfile}
        >
          <WandSparkles className="size-4" />
          {hasSavedProfile ? "저장된 피부 정보로 분석" : "피부 맞춤 분석"}
        </button>
        <button
          type="button"
          className="basic-analysis-action"
          disabled={!canChoose}
          onClick={onSkip}
        >
          <Sparkles className="size-4" />
          건너뛰고 기본 분석
        </button>
      </div>

      <button
        type="button"
        className="skin-preference-back"
        disabled={!canChoose}
        onClick={onBack}
      >
        <ArrowLeft className="size-3.5" />
        {optionName ? "옵션 다시 선택" : "상품 다시 선택"}
      </button>
    </section>
  );
}
