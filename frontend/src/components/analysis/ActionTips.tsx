import { HeartHandshake } from "lucide-react";

const tips = [
  "새 제품은 얼굴 전체 사용 전 좁은 부위에서 먼저 확인하세요.",
  "피부 반응이 나타났다면 일시적으로 사용을 중단하세요.",
  "여러 새 제품을 동시에 사용하지 마세요.",
  "붓기, 진물, 통증, 호흡 곤란 같은 증상이 있으면 의료진의 도움을 받으세요.",
];

export function ActionTips() {
  return (
    <section className="action-card">
      <div className="action-card-title">
        <span>
          <HeartHandshake className="size-5" />
        </span>
        <div>
          <p>CARE GUIDE</p>
          <h3>지금 할 수 있는 행동</h3>
        </div>
      </div>
      <ul>
        {tips.map((tip) => (
          <li key={tip}>
            <span aria-hidden="true">✓</span>
            {tip}
          </li>
        ))}
      </ul>
    </section>
  );
}
