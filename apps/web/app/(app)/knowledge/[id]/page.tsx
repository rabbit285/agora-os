"use client";

import { use } from "react";
import { useQuery } from "@tanstack/react-query";

import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { Card, CardContent } from "@/components/ui/card";
import { apiFetch } from "@/lib/api";
import type { DocumentChunk, KnowledgeDocument } from "@/lib/types";

export default function DocumentDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);

  const { data: document } = useQuery<KnowledgeDocument>({
    queryKey: ["knowledge", "documents", id],
    queryFn: () => apiFetch<KnowledgeDocument>(`/api/v1/knowledge/documents/${id}`),
  });

  const { data: chunks } = useQuery<DocumentChunk[]>({
    queryKey: ["knowledge", "documents", id, "chunks"],
    queryFn: () => apiFetch<DocumentChunk[]>(`/api/v1/knowledge/documents/${id}/chunks`),
    enabled: document?.status === "ready",
  });

  if (!document) return null;

  return (
    <div>
      <PageHeader
        title={document.title}
        description={`Classification: ${document.classification}`}
        actions={<StatusBadge status={document.status} />}
      />
      {document.error && (
        <Card className="mb-4 border-[var(--critical-50)]">
          <CardContent className="pt-6 text-sm text-[var(--critical-600)]">{document.error}</CardContent>
        </Card>
      )}
      {chunks && (
        <>
          <h2 className="mb-2 text-sm font-semibold text-[var(--fg-muted)]">
            {chunks.length} chunk{chunks.length === 1 ? "" : "s"}
          </h2>
          <div className="flex flex-col gap-2">
            {chunks.map((chunk) => (
              <Card key={chunk.id}>
                <CardContent className="pt-6">
                  <div className="mb-1 text-xs text-[var(--fg-subtle)]">
                    Chunk {chunk.chunk_index} · ~{chunk.token_count} tokens
                  </div>
                  <p className="whitespace-pre-wrap text-sm text-[var(--fg-muted)]">{chunk.content}</p>
                </CardContent>
              </Card>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
