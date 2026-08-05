"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { DataTable, type DataTableColumn } from "@/components/data-table";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
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
  const router = useRouter();
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const { data: documents, isLoading, error, refetch } = useQuery<KnowledgeDocument[]>({
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

  const columns: DataTableColumn<KnowledgeDocument>[] = [
    {
      key: "title",
      header: "Document",
      render: (doc) => (
        <div className="flex flex-col">
          <span className="font-medium">{doc.title}</span>
          {doc.error && <span className="text-xs text-[var(--critical-600)]">{doc.error}</span>}
        </div>
      ),
      sortValue: (doc) => doc.title.toLowerCase(),
    },
    {
      key: "status",
      header: "Status",
      render: (doc) => <StatusBadge status={doc.status} />,
    },
  ];

  return (
    <div>
      <PageHeader
        title="Knowledge"
        description="Uploaded documents are parsed, chunked, and embedded for future AI retrieval."
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
      {uploadError && <p className="mb-4 text-sm text-[var(--critical-600)]">{uploadError}</p>}
      <DataTable
        columns={columns}
        data={documents}
        getRowId={(doc) => doc.id}
        onRowClick={(doc) => router.push(`/knowledge/${doc.id}`)}
        isLoading={isLoading}
        error={error}
        onRetry={() => refetch()}
        emptyTitle="No documents yet"
      />
    </div>
  );
}
