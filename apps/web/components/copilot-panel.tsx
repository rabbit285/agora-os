"use client";

import { useEffect, useRef } from "react";
import { AlertCircle, Send, Sparkles, User as UserIcon } from "lucide-react";

import { ComplianceFacts, CopilotSources } from "@/components/copilot-sources";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { Citation, ComplianceFact } from "@/lib/types";

export type CopilotMessage = {
  id: string;
  role: "user" | "assistant";
  text: string;
  citations?: Citation[];
  facts?: ComplianceFact[];
  grounded?: boolean;
  provider?: string;
  isError?: boolean;
};

/** Premium conversation panel for the AI Copilot — one implementation, not
 * a page-specific chat widget. Grounding/citations are shown honestly:
 * only what the backend actually returns (no fabricated confidence score
 * or Facts/Analysis/Recommendations split, since /ai/copilot/ask returns
 * a single grounded answer, not structured sections).
 *
 * An answer can rest on two different things, and they are shown apart:
 * values read from Veyntra's compliance records, and passages from
 * uploaded documents. See components/copilot-sources.tsx. */
export function CopilotPanel({
  messages,
  onSend,
  isLoading,
  inputValue,
  onInputChange,
  suggestedPrompts,
  placeholder = "Ask a question about your uploaded documents…",
}: {
  messages: CopilotMessage[];
  onSend: (text: string) => void;
  isLoading: boolean;
  inputValue: string;
  onInputChange: (value: string) => void;
  suggestedPrompts?: string[];
  placeholder?: string;
}) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, isLoading]);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!inputValue.trim() || isLoading) return;
    onSend(inputValue.trim());
  }

  return (
    <div className="flex h-[calc(100vh-var(--header-height)-6rem)] flex-col rounded-[var(--radius-lg)] border border-[var(--border-default)] bg-[var(--bg-surface)]">
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-5 py-5">
        {messages.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-4 text-center">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-[var(--ai-50)]">
              <Sparkles className="h-5 w-5 text-[var(--ai-600)]" aria-hidden="true" />
            </div>
            <div>
              <p className="text-sm font-medium text-[var(--fg-default)]">Ask your Copilot anything</p>
              <p className="mt-1 max-w-sm text-xs text-[var(--fg-subtle)]">
                Answers are grounded in your uploaded documents, with citations showing exactly which
                sources were used.
              </p>
            </div>
            {suggestedPrompts && suggestedPrompts.length > 0 && (
              <div className="flex flex-wrap justify-center gap-2">
                {suggestedPrompts.map((prompt) => (
                  <button
                    key={prompt}
                    type="button"
                    onClick={() => onSend(prompt)}
                    className="rounded-[var(--radius-md)] border border-[var(--border-default)] bg-[var(--bg-surface)] px-3 py-1.5 text-xs text-[var(--fg-muted)] transition-colors hover:bg-[var(--bg-surface-hover)] hover:text-[var(--fg-default)]"
                  >
                    {prompt}
                  </button>
                ))}
              </div>
            )}
          </div>
        ) : (
          <div className="flex flex-col gap-4">
            {messages.map((message) => (
              <CopilotMessageBubble key={message.id} message={message} />
            ))}
            {isLoading && (
              <div className="flex items-center gap-2 text-xs text-[var(--fg-subtle)]">
                <span className="flex h-6 w-6 items-center justify-center rounded-full bg-[var(--ai-50)]">
                  <Sparkles className="h-3 w-3 animate-pulse text-[var(--ai-600)]" aria-hidden="true" />
                </span>
                Thinking…
              </div>
            )}
          </div>
        )}
      </div>
      <form
        onSubmit={handleSubmit}
        className="flex items-center gap-2 border-t border-[var(--border-default)] px-4 py-3"
      >
        <input
          value={inputValue}
          onChange={(e) => onInputChange(e.target.value)}
          placeholder={placeholder}
          className="h-9 flex-1 rounded-[var(--radius-md)] border border-[var(--border-default)] bg-[var(--bg-app)] px-3 text-sm text-[var(--fg-default)] placeholder:text-[var(--fg-subtle)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--border-focus)]"
        />
        <Button type="submit" size="icon" variant="ai" disabled={!inputValue.trim() || isLoading} aria-label="Send">
          <Send className="h-4 w-4" aria-hidden="true" />
        </Button>
      </form>
    </div>
  );
}

function CopilotMessageBubble({ message }: { message: CopilotMessage }) {
  if (message.role === "user") {
    return (
      <div className="flex items-start justify-end gap-2">
        <div className="max-w-[75%] rounded-[var(--radius-md)] bg-[var(--brand-primary)] px-3.5 py-2 text-sm text-[var(--fg-on-primary)]">
          {message.text}
        </div>
        <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[var(--gray-100)]">
          <UserIcon className="h-3 w-3 text-[var(--fg-muted)]" aria-hidden="true" />
        </span>
      </div>
    );
  }

  return (
    <div className="flex items-start gap-2">
      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[var(--ai-50)]">
        <Sparkles className="h-3 w-3 text-[var(--ai-600)]" aria-hidden="true" />
      </span>
      <div
        className={cn(
          "max-w-[85%] rounded-[var(--radius-md)] border px-3.5 py-2.5 text-sm",
          message.isError
            ? "border-[var(--critical-200)] bg-[var(--critical-50)] text-[var(--critical-700)]"
            : "border-[var(--border-default)] bg-[var(--bg-app)] text-[var(--fg-default)]",
        )}
      >
        {message.isError && (
          <div className="mb-1 flex items-center gap-1.5 text-xs font-medium">
            <AlertCircle className="h-3.5 w-3.5" aria-hidden="true" />
            Something went wrong
          </div>
        )}
        <p className="whitespace-pre-wrap">{message.text}</p>
        {!message.isError && message.provider === "demo" && (
          <div className="mt-2">
            <Badge variant="warning">Demo data</Badge>
          </div>
        )}

        {/* Veyntra's own records first: where the question was about
            compliance state, they are the answer. */}
        {message.facts && <ComplianceFacts facts={message.facts} />}

        {message.citations && (
          <CopilotSources citations={message.citations} answerLength={message.text.length} />
        )}

        {/* Only worth saying when nothing at all backed the answer. An
            answer read from the compliance records has sources — they are
            simply not documents, and "No sources found" beside a block of
            facts read straight from the database was a lie. */}
        {!message.isError &&
          message.grounded === false &&
          !message.facts?.length &&
          !message.citations?.length && (
            <p className="mt-2 text-xs text-[var(--fg-subtle)]">
              No documents or compliance records matched this question.
            </p>
          )}
      </div>
    </div>
  );
}
