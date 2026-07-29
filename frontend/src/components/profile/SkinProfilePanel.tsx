import { Check, ChevronRight, SlidersHorizontal, X } from "lucide-react";
import { useEffect, useState } from "react";
import type {
  SkinConcern,
  SkinProfile,
  SkinType,
} from "../../types/chat";

const skinTypes: Array<{ label: string; value: SkinType }> = [
  { label: "중성", value: "normal" },
  { label: "건성", value: "dry" },
  { label: "지성", value: "oily" },
  { label: "복합성", value: "combination" },
];
const concerns: Array<{ label: string; value: SkinConcern }> = [
  { label: "여드름·트러블", value: "acne_prone" },
  { label: "모공 막힘", value: "clogged_pores" },
  { label: "과도한 피지", value: "excess_sebum" },
  { label: "당김", value: "tightness" },
  { label: "각질", value: "flaking" },
  { label: "홍조", value: "redness" },
  { label: "따가움", value: "stinging" },
  { label: "가려움", value: "itching" },
];
const additionalStates = [
  {
    key: "dehydration",
    label: "수분 부족/속건조",
  },
  {
    key: "sensitive",
    label: "민감함",
  },
  {
    key: "barrierImpaired",
    label: "피부 장벽 약화",
  },
] as const;
const timings = [
  "바른 직후",
  "몇 시간 후",
  "다음 날",
  "반복 사용 후",
  "잘 모르겠음",
];
const areas = ["얼굴 전체", "눈가", "입가", "볼", "이마", "몸", "직접 입력"];

interface SkinProfilePanelProps {
  value: SkinProfile;
  onClose: () => void;
  onSave: (profile: SkinProfile) => void;
}

export function SkinProfilePanel({
  value,
  onClose,
  onSave,
}: SkinProfilePanelProps) {
  const [draft, setDraft] = useState(value);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  const toggleConcern = (concern: SkinConcern) => {
    setDraft((current) => ({
      ...current,
      concerns: current.concerns.includes(concern)
        ? current.concerns.filter((item) => item !== concern)
        : [...current.concerns, concern],
    }));
  };

  return (
    <div className="profile-overlay" role="presentation" onMouseDown={onClose}>
      <aside
        className="profile-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="profile-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="profile-header">
          <div>
            <span className="step-label">SKIN PROFILE</span>
            <h2 id="profile-title">피부 정보 설정</h2>
            <p>선택 사항이며, 맞춤 분석에만 사용해요.</p>
          </div>
          <button type="button" onClick={onClose} aria-label="피부 정보 닫기">
            <X className="size-5" />
          </button>
        </header>

        <div className="profile-fields">
          <fieldset>
            <legend>
              피부 타입 <small>선택</small>
            </legend>
            <div className="choice-grid">
              {skinTypes.map((type) => (
                <button
                  type="button"
                  key={type.value}
                  className={
                    draft.skinType === type.value ? "active" : ""
                  }
                  onClick={() =>
                    setDraft((current) => ({
                      ...current,
                      skinType:
                        current.skinType === type.value ? "" : type.value,
                    }))
                  }
                >
                  {draft.skinType === type.value && (
                    <Check className="size-3.5" />
                  )}
                  {type.label}
                </button>
              ))}
            </div>
          </fieldset>

          <fieldset>
            <legend>
              추가 피부 상태 <small>복수 선택</small>
            </legend>
            <div className="choice-grid compact">
              {additionalStates.map((state) => (
                <button
                  type="button"
                  key={state.key}
                  className={draft[state.key] ? "active" : ""}
                  onClick={() =>
                    setDraft((current) => ({
                      ...current,
                      [state.key]: !current[state.key],
                    }))
                  }
                >
                  {draft[state.key] && <Check className="size-3.5" />}
                  {state.label}
                </button>
              ))}
            </div>
          </fieldset>

          <fieldset>
            <legend>
              피부 고민 <small>복수 선택</small>
            </legend>
            <div className="choice-grid compact">
              {concerns.map((concern) => (
                <button
                  type="button"
                  key={concern.value}
                  className={
                    draft.concerns.includes(concern.value) ? "active" : ""
                  }
                  onClick={() => toggleConcern(concern.value)}
                >
                  {draft.concerns.includes(concern.value) && (
                    <Check className="size-3.5" />
                  )}
                  {concern.label}
                </button>
              ))}
            </div>
            <input
              value={draft.customSymptom}
              onChange={(event) =>
                setDraft((current) => ({
                  ...current,
                  customSymptom: event.target.value,
                }))
              }
              placeholder="다른 피부 고민이 있다면 입력해 주세요"
            />
          </fieldset>

          <label>
            <span>증상이 나타나는 시점</span>
            <select
              value={draft.symptomTiming}
              onChange={(event) =>
                setDraft((current) => ({
                  ...current,
                  symptomTiming: event.target.value,
                }))
              }
            >
              <option value="">선택하지 않음</option>
              {timings.map((timing) => (
                <option key={timing}>{timing}</option>
              ))}
            </select>
            <ChevronRight className="select-chevron size-4" />
          </label>

          <label>
            <span>알레르기 또는 민감 성분 이력</span>
            <textarea
              rows={2}
              value={draft.knownAllergies}
              onChange={(event) =>
                setDraft((current) => ({
                  ...current,
                  knownAllergies: event.target.value,
                }))
              }
              placeholder="예: 리모넨에 반응한 적이 있어요"
            />
          </label>

          <fieldset>
            <legend>제품 사용 부위</legend>
            <div className="choice-grid compact">
              {areas.map((area) => (
                <button
                  type="button"
                  key={area}
                  className={draft.productArea === area ? "active" : ""}
                  onClick={() =>
                    setDraft((current) => ({
                      ...current,
                      productArea: area,
                    }))
                  }
                >
                  {area}
                </button>
              ))}
            </div>
            {draft.productArea === "직접 입력" && (
              <input
                value={draft.customArea}
                onChange={(event) =>
                  setDraft((current) => ({
                    ...current,
                    customArea: event.target.value,
                  }))
                }
                placeholder="사용 부위를 입력해 주세요"
              />
            )}
          </fieldset>

          <label>
            <span>함께 사용하는 제품</span>
            <textarea
              rows={3}
              value={draft.currentRoutine}
              onChange={(event) =>
                setDraft((current) => ({
                  ...current,
                  currentRoutine: event.target.value,
                }))
              }
              placeholder="예: BHA 토너를 주 3회 사용 중"
            />
          </label>
        </div>

        <footer className="profile-footer">
          <button
            type="button"
            className="profile-reset"
            onClick={() =>
              setDraft({
                skinType: "",
                sensitive: false,
                dehydration: false,
                barrierImpaired: false,
                concerns: [],
                customSymptom: "",
                symptomTiming: "",
                knownAllergies: "",
                productArea: "",
                customArea: "",
                currentRoutine: "",
              })
            }
          >
            초기화
          </button>
          <button
            type="button"
            className="profile-save"
            onClick={() => {
              onSave(draft);
              onClose();
            }}
          >
            <SlidersHorizontal className="size-4" />
            분석에 반영하기
          </button>
        </footer>
      </aside>
    </div>
  );
}
