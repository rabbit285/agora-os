"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";

import { CopilotPanel, type CopilotMessage } from "@/components/copilot-panel";
import { PageHeader } from "@/components/page-header";
import { ApiError, apiFetch } from "@/lib/api";
import type { CopilotAnswer } from "@/lib/types";

const SUGGESTED_PROMPTS = [
  "What controls are missing evidence?",
  "Summarize our current security posture",
  "What's in our latest DPIA?",
];

export default function CopilotPage() {
  const [messages, setMessages] = useState<CopilotMessage[]>([]);
  const [inputValue, setInputValue] = useState("");

  const ask = useMutation({
    mutationFn: (prompt: string) =>
      apiFetch<CopilotAnswer>("/api/v1/ai/copilot/ask", { method: "POST", body: { prompt } }),
    onSuccess: (answer) => {
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          text: answer.text,
          citations: answer.citations,
          facts: answer.facts,
          grounded: answer.grounded,
          provider: answer.provider,
        },
      ]);
    },
    onError: (err) => {
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          text: err instanceof ApiError ? err.message : "Something went wrong. Please try again.",
          isError: true,
        },
      ]);
    },
  });

  function handleSend(text: string) {
    setMessages((prev) => [...prev, { id: crypto.randomUUID(), role: "user", text }]);
    setInputValue("");
    ask.mutate(text);
  }

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="AI Copilot"
        description="Answers come from your compliance records and your uploaded documents. Every answer shows which."
      />
      <CopilotPanel
        messages={messages}
        onSend={handleSend}
        isLoading={ask.isPending}
        inputValue={inputValue}
        onInputChange={setInputValue}
        suggestedPrompts={SUGGESTED_PROMPTS}
      />
    </div>
  );
}
