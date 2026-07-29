import type { ChatMessage } from "../types/chat";

export function removeAnalysisMessages(
  messages: ChatMessage[],
): ChatMessage[] {
  return messages.filter(
    (message) => message.kind !== "analysis"
  );
}
