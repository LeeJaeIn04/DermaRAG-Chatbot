import type { ChatRequest, ChatResponse } from "../types/chat";
import { apiRequest } from "./client";

export function sendChat(request: ChatRequest) {
  return apiRequest<ChatResponse>("/chat", {
    method: "POST",
    body: JSON.stringify(request),
  });
}
