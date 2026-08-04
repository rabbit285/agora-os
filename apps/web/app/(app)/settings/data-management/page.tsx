"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { ApiError, apiFetch } from "@/lib/api";
import { REPORT_FORMATS, type OrganizationSettings } from "@/lib/types";

function ExportSection() {
  const [format, setFormat] = useState<string>(REPORT_FORMATS[2]); // xlsx

  const exportData = useMutation({
    mutationFn: () =>
      apiFetch<{ download_url: string }>(`/api/v1/organizations/current/data-export?format=${format}`),
    onSuccess: (data) => {
      window.location.href = data.download_url;
    },
  });

  return (
    <Card className="mb-6 max-w-2xl">
      <CardContent className="flex flex-col gap-3 pt-6">
        <h2 className="text-sm font-semibold text-neutral-900">Export organization data</h2>
        <p className="text-xs text-neutral-500">
          spec §B5 — a real, downloadable bundle of your organization&apos;s own data across every
          module: members, compliance records, security data, sales, support, knowledge, automation,
          business memory, and business rules.
        </p>
        <div className="flex items-center gap-2">
          <Select value={format} onChange={(e) => setFormat(e.target.value)} className="w-32">
            {REPORT_FORMATS.map((f) => (
              <option key={f} value={f}>
                {f.toUpperCase()}
              </option>
            ))}
          </Select>
          <Button size="sm" disabled={exportData.isPending} onClick={() => exportData.mutate()}>
            {exportData.isPending ? "Generating…" : "Download export"}
          </Button>
        </div>
        {exportData.isError && (
          <p className="text-sm text-red-600">
            {exportData.error instanceof ApiError ? exportData.error.message : "Could not generate export."}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function DeletionSection() {
  const queryClient = useQueryClient();
  const { data: org } = useQuery<OrganizationSettings>({
    queryKey: ["organizations", "current"],
    queryFn: () => apiFetch<OrganizationSettings>("/api/v1/organizations/current"),
  });
  const [confirmName, setConfirmName] = useState("");

  const requestDeletion = useMutation({
    mutationFn: () =>
      apiFetch<OrganizationSettings>("/api/v1/organizations/current/deletion-request", {
        method: "POST",
        body: { confirm_name: confirmName },
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["organizations", "current"] });
      setConfirmName("");
    },
  });

  const cancelDeletion = useMutation({
    mutationFn: () =>
      apiFetch<OrganizationSettings>("/api/v1/organizations/current/deletion-request/cancel", {
        method: "POST",
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["organizations", "current"] }),
  });

  const executeDeletion = useMutation({
    mutationFn: () =>
      apiFetch("/api/v1/organizations/current/deletion-request/execute", {
        method: "POST",
        body: { confirm_name: confirmName },
      }),
    onSuccess: () => {
      window.location.href = "/login";
    },
  });

  const pending = org?.deletion_requested_at != null;

  return (
    <Card className="max-w-2xl border-red-300">
      <CardContent className="flex flex-col gap-3 pt-6">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold text-red-700">Delete organization</h2>
          {pending && <Badge variant="destructive">Deletion requested</Badge>}
        </div>
        <p className="text-xs text-neutral-500">
          spec §B5 — permanently deletes this organization and every record it owns across every
          module. This does not delete member user accounts themselves (a login identity is separate
          from organization membership). Irreversible once executed.
        </p>

        {pending ? (
          <>
            <p className="text-xs text-neutral-600">
              Deletion requested at {org?.deletion_requested_at}. Cancel below, or type the
              organization&apos;s exact name to permanently execute the deletion now.
            </p>
            <Input
              placeholder="Type the organization name to confirm"
              value={confirmName}
              onChange={(e) => setConfirmName(e.target.value)}
            />
            <div className="flex gap-2">
              <Button size="sm" variant="outline" disabled={cancelDeletion.isPending} onClick={() => cancelDeletion.mutate()}>
                Cancel deletion request
              </Button>
              <Button
                size="sm"
                variant="destructive"
                disabled={!confirmName.trim() || executeDeletion.isPending}
                onClick={() => executeDeletion.mutate()}
              >
                Permanently delete now
              </Button>
            </div>
          </>
        ) : (
          <>
            <Input
              placeholder="Type the organization name to confirm"
              value={confirmName}
              onChange={(e) => setConfirmName(e.target.value)}
            />
            <div>
              <Button
                size="sm"
                variant="destructive"
                disabled={!confirmName.trim() || requestDeletion.isPending}
                onClick={() => requestDeletion.mutate()}
              >
                Request deletion
              </Button>
            </div>
          </>
        )}
        {(requestDeletion.isError || executeDeletion.isError) && (
          <p className="text-sm text-red-600">
            {requestDeletion.error instanceof ApiError
              ? requestDeletion.error.message
              : executeDeletion.error instanceof ApiError
                ? executeDeletion.error.message
                : "Could not complete the request."}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

export default function DataManagementPage() {
  return (
    <div>
      <PageHeader
        title="Data Management"
        description="spec §67 — export your organization's data, or permanently delete it."
      />
      <ExportSection />
      <DeletionSection />
    </div>
  );
}
