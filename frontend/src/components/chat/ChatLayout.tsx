import {
  Clock3,
  Leaf,
  Menu,
  MessageSquarePlus,
  PanelLeftClose,
  Settings2,
  ShieldCheck,
} from "lucide-react";
import { useState, type ReactNode } from "react";

interface RecentAnalysis {
  id: string;
  productName: string;
}

interface ChatLayoutProps {
  children: ReactNode;
  composer: ReactNode;
  profileConfigured: boolean;
  recentAnalyses: RecentAnalysis[];
  onNewChat: () => void;
  onOpenProfile: () => void;
}

export function ChatLayout({
  children,
  composer,
  profileConfigured,
  recentAnalyses,
  onNewChat,
  onOpenProfile,
}: ChatLayoutProps) {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const sidebar = (
    <aside className="app-sidebar">
      <div className="sidebar-brand">
        <span className="sidebar-logo">
          <Leaf className="size-5" strokeWidth={1.8} />
        </span>
        <div>
          <strong>DermaRAG</strong>
          <span>Ingredient clarity</span>
        </div>
        <button
          type="button"
          className="mobile-close"
          onClick={() => setMobileMenuOpen(false)}
          aria-label="메뉴 닫기"
        >
          <PanelLeftClose className="size-5" />
        </button>
      </div>

      <button
        type="button"
        className="new-chat-button"
        onClick={() => {
          onNewChat();
          setMobileMenuOpen(false);
        }}
      >
        <MessageSquarePlus className="size-4" />
        새 대화
        <span>+</span>
      </button>

      <div className="sidebar-section">
        <div className="sidebar-label">
          <span>최근 분석</span>
          <Clock3 className="size-3.5" />
        </div>
        {recentAnalyses.length ? (
          <nav className="recent-list" aria-label="최근 분석">
            {recentAnalyses.map((item) => (
              <button
                type="button"
                key={item.id}
                onClick={() => {
                  document
                    .getElementById(item.id)
                    ?.scrollIntoView({ behavior: "smooth", block: "start" });
                  setMobileMenuOpen(false);
                }}
              >
                <span>{item.productName.slice(0, 1)}</span>
                <p>{item.productName}</p>
              </button>
            ))}
          </nav>
        ) : (
          <div className="recent-empty">
            <p>아직 분석한 제품이 없어요.</p>
            <span>첫 제품을 검색해 보세요.</span>
          </div>
        )}
      </div>

      <div className="sidebar-trust">
        <ShieldCheck className="size-5" />
        <div>
          <strong>식약처 데이터 기반</strong>
          <p>성분 근거와 규제 정보를 함께 확인해요.</p>
        </div>
      </div>
    </aside>
  );

  return (
    <div className="app-shell">
      <div className="desktop-sidebar">{sidebar}</div>
      {mobileMenuOpen && (
        <div
          className="mobile-sidebar-overlay"
          role="presentation"
          onMouseDown={() => setMobileMenuOpen(false)}
        >
          <div onMouseDown={(event) => event.stopPropagation()}>{sidebar}</div>
        </div>
      )}

      <main className="chat-main">
        <header className="topbar">
          <div className="topbar-left">
            <button
              type="button"
              className="menu-button"
              onClick={() => setMobileMenuOpen(true)}
              aria-label="메뉴 열기"
            >
              <Menu className="size-5" />
            </button>
            <div className="mobile-brand">
              <span>
                <Leaf className="size-4" />
              </span>
              DermaRAG
            </div>
            <div className="desktop-page-title">
              <span className="live-dot" />
              성분 분석 어시스턴트
            </div>
          </div>
          <button
            type="button"
            className={`profile-button ${profileConfigured ? "configured" : ""}`}
            onClick={onOpenProfile}
          >
            <Settings2 className="size-4" />
            <span>피부 정보</span>
            {profileConfigured && <i aria-label="설정 완료" />}
          </button>
        </header>

        <div className="chat-scroll">{children}</div>
        {composer}
      </main>
    </div>
  );
}
