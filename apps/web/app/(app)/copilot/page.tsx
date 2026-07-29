"use client";

import Link from "next/link";
import { useState } from "react";
import { useMutation } from "@tanstack/react-query";

import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ApiError, apiFetch } from "@/lib/api";
import type { CopilotAnswer } from "@/lib/types";

export default function CopilotPage() {
  const [question, setQuestion] = useState("");
  const [error, setError] = useState<string | null>(null);

  const ask = useMutation({
    mutationFn: (prompt: string) =>
      apiFetch<CopilotAnswer>("/api/v1/ai/copilot/ask", { method: "POST", body: { prompt } }),
    onError: (err) => setError(err instanceof ApiError ? err.message : "Something went wrong"),
  });

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!question.trim()) return;
    setError(null);
    ask.mutate(question.trim());
  }

  return (
    <div>
      <PageHeader
        title="AI Copilot"
        description="Answers are grounded in your uploaded documents — citations show exactly which chunks were used (spec sections 8-9)."
      />
      <form onSubmit={handleSubmit} className="mb-6 flex gap-2">
        <Input
          placeholder="Ask a question about your uploaded documents…"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
        />
        <Button type="submit" disabled={!question.trim() || ask.isPending}>
          {ask.isPending ? "Asking…" : "Ask"}
        </Button>
      </form>

      {error && <p className="mb-4 text-sm text-red-600">{error}</p>}

      {ask.data && (
        <Card>
          <CardContent className="pt-6">
            <div className="mb-3 flex items-center gap-2">
              {ask.data.provider === "demo" && <Badge variant="warning">Demo data</Badge>}
              {!ask.data.grounded && <Badge variant="outline">No sources found</Badge>}
              {ask.data.grounded && (
                <Badge variant="secondary">
                  {ask.data.citations.length} source{ask.data.citations.length === 1 ? "" : "s"}
                </Badge>
              )}
            </div>
            <p className="whitespace-pre-wrap text-sm text-neutral-800">{ask.data.text}</p>

            {ask.data.citations.length > 0 && (
              <div className="mt-4 border-t border-neutral-100 pt-4">
                <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-neutral-400">
                  Sources
                </h3>
                <ul className="flex flex-col gap-1">
                  {ask.data.citations.map((citation) => (
                    <li key={citation.chunk_id}>
                      <Link
                        href={`/knowledge/${citation.document_id}`}
                        className="text-sm text-neutral-600 hover:underline"
                      >
                        Document {citation.document_id.slice(0, 8)} · chunk {citation.chunk_index}
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
