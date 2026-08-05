"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { apiFetch } from "@/lib/api";
import type { KnowledgeArticle } from "@/lib/types";

export default function SupportKnowledgeBasePage() {
  const queryClient = useQueryClient();
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [category, setCategory] = useState("");

  const { data: articles } = useQuery<KnowledgeArticle[]>({
    queryKey: ["support", "knowledge-articles"],
    queryFn: () => apiFetch<KnowledgeArticle[]>("/api/v1/support/knowledge-articles"),
  });

  const createArticle = useMutation({
    mutationFn: () =>
      apiFetch<KnowledgeArticle>("/api/v1/support/knowledge-articles", {
        method: "POST",
        body: { title, body, category: category || null },
      }),
    onSuccess: () => {
      setTitle("");
      setBody("");
      setCategory("");
      queryClient.invalidateQueries({ queryKey: ["support", "knowledge-articles"] });
    },
  });

  const togglePublished = useMutation({
    mutationFn: ({ id, published }: { id: string; published: boolean }) =>
      apiFetch(`/api/v1/support/knowledge-articles/${id}`, {
        method: "PATCH",
        body: { published },
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["support", "knowledge-articles"] }),
  });

  return (
    <div>
      <PageHeader
        title="Support Knowledge Base"
        description="Internal articles used by agents and the AI Agent's grounded replies (spec §32)."
      />
      <Card className="mb-4">
        <CardContent className="flex flex-col gap-3 pt-6">
          <Input
            placeholder="Article title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
          <Input
            placeholder="Category (optional)"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
          />
          <Textarea
            placeholder="Article body"
            value={body}
            onChange={(e) => setBody(e.target.value)}
          />
          <Button
            disabled={!title.trim() || !body.trim() || createArticle.isPending}
            onClick={() => createArticle.mutate()}
            className="self-start"
          >
            Create article
          </Button>
        </CardContent>
      </Card>
      {articles?.length === 0 && (
        <p className="text-sm text-[var(--fg-muted)]">No knowledge articles yet.</p>
      )}
      <div className="flex flex-col gap-2">
        {articles?.map((article) => (
          <Card key={article.id}>
            <CardContent className="pt-6">
              <div className="mb-1 flex items-center justify-between">
                <div className="font-medium text-[var(--fg-default)]">{article.title}</div>
                <div className="flex items-center gap-2">
                  <StatusBadge status={article.published ? "published" : "draft"} />
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={togglePublished.isPending}
                    onClick={() =>
                      togglePublished.mutate({ id: article.id, published: !article.published })
                    }
                  >
                    {article.published ? "Unpublish" : "Publish"}
                  </Button>
                </div>
              </div>
              {article.category && (
                <div className="mb-1 text-xs text-[var(--fg-subtle)]">{article.category}</div>
              )}
              <p className="text-sm text-[var(--fg-muted)]">{article.body}</p>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
