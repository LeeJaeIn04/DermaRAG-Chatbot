import { ArrowUpRight, FlaskConical, Leaf, ShieldCheck } from "lucide-react";

const examples = [
  {
    icon: Leaf,
    text: "라운드랩 자작나무 선크림이 민감성 피부에 괜찮은지 알려줘",
  },
  {
    icon: FlaskConical,
    text: "이 제품을 바르면 눈가가 따가운데 어떤 성분을 확인해야 할까?",
  },
  {
    icon: ShieldCheck,
    text: "리모넨 알레르기 이력이 있는데 이 제품을 써도 될까?",
  },
];

interface EmptyStateProps {
  onExampleClick: (question: string) => void;
}

export function EmptyState({ onExampleClick }: EmptyStateProps) {
  return (
    <section className="empty-state">
      <div className="brand-orbit" aria-hidden="true">
        <div className="brand-orbit-inner">
          <Leaf className="size-7" strokeWidth={1.8} />
        </div>
      </div>
      <p className="eyebrow">INGREDIENT INTELLIGENCE</p>
      <h1>내 피부를 위한<br className="sm:hidden" /> 성분 분석</h1>
      <p className="empty-subtitle">
        궁금한 화장품이나 피부 반응을 알려주세요.
        <br className="hidden sm:block" />
        식약처 성분 데이터를 바탕으로 차분하게 살펴볼게요.
      </p>

      <div className="example-grid">
        {examples.map(({ icon: Icon, text }) => (
          <button
            type="button"
            className="example-card"
            key={text}
            onClick={() => onExampleClick(text)}
          >
            <span className="example-icon">
              <Icon className="size-5" strokeWidth={1.8} />
            </span>
            <span>{text}</span>
            <ArrowUpRight className="example-arrow size-4" />
          </button>
        ))}
      </div>
    </section>
  );
}
