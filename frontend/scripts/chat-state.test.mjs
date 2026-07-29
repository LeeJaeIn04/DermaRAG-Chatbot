import assert from "node:assert/strict";
import test from "node:test";
import {
  removeAnalysisMessages,
} from "../src/utils/chat.ts";

test("새 상품·옵션 분석을 시작할 때 이전 분석 결과를 제거한다", () => {
  const messages = [
    {
      id: "question",
      role: "user",
      kind: "text",
      content: "질문",
      createdAt: new Date(),
    },
    {
      id: "analysis",
      role: "assistant",
      kind: "analysis",
      analysis: {},
      createdAt: new Date(),
    },
    {
      id: "options",
      role: "assistant",
      kind: "text",
      content: "옵션을 선택해 주세요.",
      createdAt: new Date(),
    },
  ];

  const result = removeAnalysisMessages(messages);

  assert.deepEqual(
    result.map((message) => message.id),
    ["question", "options"],
  );
});
