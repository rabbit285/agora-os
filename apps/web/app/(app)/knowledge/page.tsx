"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ApiError, apiFetch } from "@/lib/api";
import type { KnowledgeDocument } from "@/lib/types";

const IN_FLIGHT_STATUSES = new Set(["pending", "processing"]);

async function uploadFile(file: File): Promise<void> {
  const { file_id, upload_url } = await apiFetch<{ file_id: string; upload_url: string }>(
    "/api/v1/files/upload-url",
    {
      method: "POST",
      body: {
        filename: file.name,
        content_type: file.type || "application/octet-stream",
        size_bytes: file.size,
        classification: "internal",
      },
    },
  );

  const putResponse = await fetch(upload_url, {
    method: "PUT",
    headers: { "Content-Type": file.type || "application/octet-stream" },
    body: file,
  });
  if (!putResponse.ok) {
    throw new Error(`Upload to storage failed with status ${putResponse.status}`);
  }

  await apiFetch("/api/v1/knowledge/documents", {
    method: "POST",
    body: { file_id, title: file.name },
  });
}

export default function KnowledgePage() {
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const { data: documents } = useQuery<KnowledgeDocument[]>({
    queryKey: ["knowledge", "documents"],
    queryFn: () => apiFetch<KnowledgeDocument[]>("/api/v1/knowledge/documents"),
    refetchInterval: (query) => {
      const docs = query.state.data ?? [];
      return docs.some((d) => IN_FLIGHT_STATUSES.has(d.status)) ? 2000 : false;
    },
  });

  const upload = useMutation({
    mutationFn: uploadFile,
    onSuccess: () => {
      setUploadError(null);
      queryClient.invalidateQueries({ queryKey: ["knowledge", "documents"] });
    },
    onError: (error) => {
      setUploadError(error instanceof ApiError ? error.message : "Upload failed");
    },
  });

  return (
    <div>
      <PageHeader
        title="Knowledge"
        description="Uploaded documents are parsed, chunked, and embedded for future AI retrieval (spec section 46)."
        actions={
          <>
            <input
              ref={fileInputRef}
              type="file"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) upload.mutate(file);
                e.target.value = "";
              }}
            />
            <Button onClick={() => fileInputRef.current?.click()} disabled={upload.isPending}>
              {upload.isPending ? "Uploading…" : "Upload document"}
            </Button>
          </>
        }
      />
      {uploadError && <p className="mb-4 text-sm text-red-600">{uploadError}</p>}
      {documents && documents.length === 0 && (
        <p className="text-sm text-neutral-500">No documents yet.</p>
      )}
      <div className="flex flex-col gap-2">
        {documents?.map((doc) => (
          <Link key={doc.id} href={`/knowledge/${doc.id}`}>
            <Card className="transition-colors hover:border-neutral-400">
              <CardContent className="flex items-center justify-between pt-6">
                <div>
                  <div className="font-medium text-neutral-900">{doc.title}</div>
                  {doc.error && <div className="text-xs text-red-600">{doc.error}</div>}
                </div>
                <StatusBadge status={doc.status} />
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}
