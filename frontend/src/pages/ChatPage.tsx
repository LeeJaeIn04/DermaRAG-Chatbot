import { useEffect, useMemo, useRef, useState } from "react";
import { ChatInput } from "../components/chat/ChatInput";
import { ChatLayout } from "../components/chat/ChatLayout";
import { ChatMessage } from "../components/chat/ChatMessage";
import { EmptyState } from "../components/chat/EmptyState";
import { TypingIndicator } from "../components/chat/TypingIndicator";
import { SkinProfilePanel } from "../components/profile/SkinProfilePanel";
import { useProductAnalysisChat } from "../hooks/useProductAnalysisChat";
import type { SkinProfile } from "../types/chat";

const emptyProfile: SkinProfile = {
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
};

export function ChatPage() {
  const [profile, setProfile] = useState<SkinProfile>(emptyProfile);
  const [profileOpen, setProfileOpen] = useState(false);
  const scrollEndRef = useRef<HTMLDivElement>(null);
  const {
    messages,
    flowState,
    selectedProduct,
    selectedOption,
    recentAnalyses,
    submitQuestion,
    chooseProduct,
    chooseOption,
    startNewChat,
    isBusy,
  } = useProductAnalysisChat(profile);

  const profileConfigured = useMemo(
    () =>
      Boolean(
        profile.skinType ||
          profile.sensitive ||
          profile.dehydration ||
          profile.barrierImpaired ||
          profile.concerns.length ||
          profile.customSymptom ||
          profile.symptomTiming ||
          profile.knownAllergies ||
          profile.productArea ||
          profile.currentRoutine,
      ),
    [profile],
  );

  useEffect(() => {
    scrollEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [flowState, messages]);

  const isInitial = messages.length === 1 && messages[0].id === "welcome";

  return (
    <>
      <ChatLayout
        profileConfigured={profileConfigured}
        recentAnalyses={recentAnalyses}
        onNewChat={startNewChat}
        onOpenProfile={() => setProfileOpen(true)}
        composer={<ChatInput onSubmit={submitQuestion} isBusy={isBusy} />}
      >
        <div className={`conversation ${isInitial ? "is-initial" : ""}`}>
          {isInitial ? (
            <EmptyState onExampleClick={submitQuestion} />
          ) : (
            messages
              .filter((message) => message.id !== "welcome")
              .map((message) => (
                <div id={message.id} key={message.id} className="message-anchor">
                  <ChatMessage
                    message={message}
                    selectedProduct={selectedProduct}
                    canSelectProduct={
                      flowState === "waiting_for_product_selection"
                    }
                    onProductSelect={chooseProduct}
                    canSelectOption={
                      flowState === "waiting_for_option_selection" &&
                      !selectedOption
                    }
                    onOptionSelect={chooseOption}
                  />
                </div>
              ))
          )}
          <TypingIndicator state={flowState} />
          <div ref={scrollEndRef} />
        </div>
      </ChatLayout>

      {profileOpen && (
        <SkinProfilePanel
          value={profile}
          onClose={() => setProfileOpen(false)}
          onSave={setProfile}
        />
      )}
    </>
  );
}
