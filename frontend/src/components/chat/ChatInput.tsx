import { ArrowUp, Paperclip } from "lucide-react";
import { useState } from "react";

interface ChatInputProps {
  onSubmit: (message: string) => void;
  isBusy: boolean;
}

export function ChatInput({
  onSubmit,
  isBusy,
}: ChatInputProps) {
  const [value, setValue] = useState("");

  const submit = () => {
    if (!value.trim() || isBusy) return;
    onSubmit(value);
    setValue("");
  };

  return (
    <div className="composer-wrap">
      <div className="composer">
        <button
          type="button"
          className="composer-icon hidden sm:grid"
          aria-label="파일 첨부는 준비 중입니다"
          disabled
        >
          <Paperclip className="size-5" />
        </button>
        <textarea
          rows={1}
          value={value}
          disabled={isBusy}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              submit();
            }
          }}
          placeholder={
            isBusy
              ? "분석이 끝날 때까지 잠시 기다려 주세요"
              : "궁금한 제품이나 피부 반응을 입력해 주세요"
          }
          aria-label="화장품 분석 질문"
          className="composer-input"
        />
        <button
          type="button"
          onClick={submit}
          className="send-button"
          aria-label="메시지 전송"
          disabled={!value.trim() || isBusy}
        >
          <ArrowUp className="size-5" strokeWidth={2.4} />
        </button>
      </div>
      <p className="composer-note">
        DermaRAG의 정보는 일반적인 참고용이며 의료 진단을 대신하지 않습니다.
      </p>
    </div>
  );
}
