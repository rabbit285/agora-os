"use client";

import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Upload } from "lucide-react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { apiFetch } from "@/lib/api";
import type { ImportJobOut, ImportPreviewOut } from "@/lib/types";

const COMPANY_TARGET_FIELDS = ["name", "domain", "website", "industry", "employee_count", "location"];
const PERSON_TARGET_FIELDS = [
  "full_name",
  "email",
  "title",
  "company_domain",
  "location",
  "phone",
];

const IN_FLIGHT_STATUSES = new Set(["pending", "running"]);

async function uploadFile(file: File): Promise<string> {
  const { file_id, upload_url } = await apiFetch<{ file_id: string; upload_url: string }>(
    "/api/v1/files/upload-url",
    {
      method: "POST",
      body: {
        filename: file.name,
        content_type: file.type || "text/csv",
        size_bytes: file.size,
        classification: "internal",
      },
    },
  );
  const putResponse = await fetch(upload_url, {
    method: "PUT",
    headers: { "Content-Type": file.type || "text/csv" },
    body: file,
  });
  if (!putResponse.ok) throw new Error(`Upload to storage failed with status ${putResponse.status}`);
  return file_id;
}

/** CSV import (spec §13): upload -> column-mapping preview (always
 * user-confirmable, never auto-applied) -> validation -> import, with
 * per-row errors surfaced rather than failing the whole file. Large
 * files run through a Temporal workflow on the backend
 * (`_SYNC_IMPORT_MAX_ROWS`); this dialog polls the job either way so the
 * UI is identical whether the import finished instantly or is still
 * running. */
export function ImportDialog({
  open,
  onOpenChange,
  recordType,
  onImported,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  recordType: "company" | "person";
  onImported: () => void;
}) {
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [fileId, setFileId] = useState<string | null>(null);
  const [preview, setPreview] = useState<ImportPreviewOut | null>(null);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [jobId, setJobId] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const targetFields = recordType === "company" ? COMPANY_TARGET_FIELDS : PERSON_TARGET_FIELDS;

  const upload = useMutation({
    mutationFn: async (file: File) => {
      setUploadError(null);
      const id = await uploadFile(file);
      setFileId(id);
      return apiFetch<ImportPreviewOut>("/api/v1/sales/lead-finder/import/preview", {
        method: "POST",
        body: { file_id: id, record_type: recordType },
      });
    },
    onSuccess: (data) => {
      setPreview(data);
      const initialMapping: Record<string, string> = {};
      for (const field of targetFields) {
        if (data.suggested_mapping[field]) initialMapping[field] = data.suggested_mapping[field] as string;
      }
      setMapping(initialMapping);
    },
    onError: (err) => setUploadError(err instanceof Error ? err.message : "Upload failed"),
  });

  const startImport = useMutation({
    mutationFn: () =>
      apiFetch<ImportJobOut>("/api/v1/sales/lead-finder/import", {
        method: "POST",
        body: { file_id: fileId, record_type: recordType, column_mapping: mapping },
      }),
    onSuccess: (job) => setJobId(job.id),
  });

  const jobStatus = useQuery<ImportJobOut>({
    queryKey: ["sales", "lead-finder", "import-jobs", jobId],
    queryFn: () => apiFetch<ImportJobOut>(`/api/v1/sales/lead-finder/import-jobs/${jobId}`),
    enabled: jobId !== null,
    refetchInterval: (query) => (IN_FLIGHT_STATUSES.has(query.state.data?.status ?? "pending") ? 2000 : false),
  });

  function reset() {
    setFileId(null);
    setPreview(null);
    setMapping({});
    setJobId(null);
    setUploadError(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  const job = jobStatus.data;
  if (job && job.status !== "running" && job.status !== "pending" && jobId) {
    queryClient.invalidateQueries({ queryKey: ["sales", "lead-finder", recordType === "company" ? "companies" : "people"] });
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) reset();
        onOpenChange(next);
      }}
    >
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>Import {recordType === "company" ? "companies" : "people"} from CSV</DialogTitle>
          <DialogDescription>
            Imported records are labeled &quot;user entered&quot; — never presented as provider-verified.
          </DialogDescription>
        </DialogHeader>

        {!preview && !job && (
          <div>
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv,text/csv"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) upload.mutate(file);
              }}
              className="hidden"
            />
            <Button
              variant="outline"
              disabled={upload.isPending}
              onClick={() => fileInputRef.current?.click()}
            >
              <Upload className="h-3.5 w-3.5" />
              {upload.isPending ? "Uploading…" : "Choose CSV file"}
            </Button>
            {uploadError && <p className="mt-2 text-xs text-[var(--critical-700)]">{uploadError}</p>}
          </div>
        )}

        {preview && !job && (
          <div className="flex flex-col gap-3">
            <p className="text-xs text-[var(--fg-muted)]">
              {preview.total_rows} rows detected. Confirm which column maps to each field.
            </p>
            <div className="grid grid-cols-2 gap-2">
              {targetFields.map((field) => (
                <div key={field}>
                  <label
                    htmlFor={`import-mapping-${field}`}
                    className="mb-1 block text-xs font-medium capitalize text-[var(--fg-default)]"
                  >
                    {field.replace(/_/g, " ")}
                  </label>
                  <Select
                    id={`import-mapping-${field}`}
                    value={mapping[field] ?? ""}
                    onChange={(e) => setMapping((m) => ({ ...m, [field]: e.target.value }))}
                  >
                    <option value="">Not mapped</option>
                    {preview.headers.map((header) => (
                      <option key={header} value={header}>
                        {header}
                      </option>
                    ))}
                  </Select>
                </div>
              ))}
            </div>
            {preview.sample_rows.length > 0 && (
              <div className="max-h-32 overflow-y-auto rounded-[var(--radius-md)] border border-[var(--border-default)] p-2 text-[11px] text-[var(--fg-muted)]">
                {preview.sample_rows.slice(0, 3).map((row, i) => (
                  <pre key={i} className="whitespace-pre-wrap break-words">
                    {JSON.stringify(row)}
                  </pre>
                ))}
              </div>
            )}
          </div>
        )}

        {job && (
          <div className="rounded-[var(--radius-md)] border border-[var(--border-default)] bg-[var(--bg-sunken)] p-3 text-sm">
            <p className="mb-1">
              Status: <Badge variant="outline">{job.status}</Badge>
            </p>
            <p className="text-xs text-[var(--fg-muted)]">
              {job.imported_rows} imported, {job.skipped_rows} skipped of {job.total_rows} rows.
            </p>
            {job.error_rows.length > 0 && (
              <ul className="mt-2 max-h-32 list-disc overflow-y-auto pl-4 text-[11px] text-[var(--critical-700)]">
                {job.error_rows.map((e) => (
                  <li key={e.row_number}>
                    Row {e.row_number}: {e.error}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        <DialogFooter>
          {job ? (
            <Button
              onClick={() => {
                onImported();
                reset();
                onOpenChange(false);
              }}
            >
              Done
            </Button>
          ) : (
            <>
              <Button variant="outline" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              {preview && (
                <Button disabled={!fileId || startImport.isPending} onClick={() => startImport.mutate()}>
                  {startImport.isPending ? "Starting…" : "Import"}
                </Button>
              )}
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
