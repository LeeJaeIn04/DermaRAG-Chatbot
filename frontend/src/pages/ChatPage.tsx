import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ChatInput } from "../components/chat/ChatInput";
import { ChatLayout } from "../components/chat/ChatLayout";
import { ChatMessage } from "../components/chat/ChatMessage";
import { EmptyState } from "../components/chat/EmptyState";
import { TypingIndicator } from "../components/chat/TypingIndicator";
import { SkinProfilePanel } from "../components/profile/SkinProfilePanel";
import { useProductAnalysisChat } from "../hooks/useProductAnalysisChat";
import type { SkinProfile } from "../types/chat";
import { hasSkinProfileData, summarizeSkinProfile } from "../utils/skin";

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
  const [profilePanelMode, setProfilePanelMode] = useState<
    "global" | "analysis" | null
  >(null);
  const requestProfileForAnalysis = useCallback(() => {
    setProfilePanelMode("analysis");
  }, []);
  const scrollEndRef = useRef<HTMLDivElement>(null);
  const {
    messages,
    flowState,
    selectedProduct,
    selectedOption,
    activeSkinPreferenceMessageId,
    retryMessageId,
    canRetryAnalysis,
    recentAnalyses,
    submitQuestion,
    chooseProduct,
    chooseOption,
    useSkinProfileForPendingAnalysis,
    skipSkinProfileForPendingAnalysis,
    completeSkinProfileForPendingAnalysis,
    cancelSkinProfileEntry,
    goBackFromSkinPreference,
    retryAnalysis,
    startNewChat,
    isBusy,
  } = useProductAnalysisChat(profile, requestProfileForAnalysis);

  const profileConfigured = useMemo(() => hasSkinProfileData(profile), [profile]);
  const profileSummary = useMemo(() => summarizeSkinProfile(profile), [profile]);

  useEffect(() => {
    scrollEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [flowState, messages]);

  const saveProfile = (savedProfile: SkinProfile) => {
    const mode = profilePanelMode;
    setProfile(savedProfile);
    setProfilePanelMode(null);
    if (mode === "analysis") {
      completeSkinProfileForPendingAnalysis(savedProfile);
    }
  };

  const closeProfilePanel = () => {
    const mode = profilePanelMode;
    setProfilePanelMode(null);
    if (mode === "analysis") {
      cancelSkinProfileEntry();
    }
  };

  const isInitial = messages.length === 1 && messages[0].id === "welcome";

  return (
    <>
      <ChatLayout
        profileConfigured={profileConfigured}
        recentAnalyses={recentAnalyses}
        onNewChat={startNewChat}
        onOpenProfile={() => setProfilePanelMode("global")}
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
                    activeSkinPreferenceMessageId={
                      flowState === "waiting_for_skin_preference"
                        ? activeSkinPreferenceMessageId
                        : null
                    }
                    profileSummary={profileSummary}
                    onUseSkinProfile={useSkinProfileForPendingAnalysis}
                    onSkipSkinProfile={skipSkinProfileForPendingAnalysis}
                    onBackFromSkinPreference={goBackFromSkinPreference}
                    retryMessageId={retryMessageId}
                    canRetryAnalysis={canRetryAnalysis}
                    onRetryAnalysis={retryAnalysis}
                  />
                </div>
              ))
          )}
          <TypingIndicator state={flowState} />
          <div ref={scrollEndRef} />
        </div>
      </ChatLayout>

      {profilePanelMode && (
        <SkinProfilePanel
          value={profile}
          analysisMode={profilePanelMode === "analysis"}
          onClose={closeProfilePanel}
          onSave={saveProfile}
        />
      )}
    </>
  );
}
