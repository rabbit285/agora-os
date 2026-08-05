"use client";

import { useQuery } from "@tanstack/react-query";

import { StatusBadge } from "@/components/status-badge";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { ApiError, apiFetch } from "@/lib/api";
import type { ProvenanceOut } from "@/lib/types";

/** How a saved Account/Contact was originally found — provider, source
 * URL, retrieval/verification timestamps (spec: provenance must be
 * visible on the record, never fabricated). Renders nothing (not an
 * error state) when the record predates the Lead Finder or was created
 * some other way — a missing provenance row is an expected, honest
 * outcome, not a failure. */
export function ProvenanceCard({
  recordType,
  recordId,
}: {
  recordType: "account" | "contact";
  recordId: string;
}) {
  const { data, error } = useQuery<ProvenanceOut>({
    queryKey: ["sales", "lead-finder", "provenance", recordType, recordId],
    queryFn: () => apiFetch<ProvenanceOut>(`/api/v1/sales/lead-finder/provenance/${recordType}/${recordId}`),
    retry: false,
  });

  if (error instanceof ApiError && error.status === 404) return null;
  if (!data) return null;

  return (
    <Card className="mb-6">
      <CardContent className="pt-6">
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
          Source &amp; Provenance
        </h2>
        <div className="flex flex-wrap items-center gap-2 text-xs text-[var(--fg-muted)]">
          <Badge variant="outline" className="capitalize">
            {data.provider}
          </Badge>
          <StatusBadge status={data.verification_status} />
          {data.enrichment_status !== "none" && <StatusBadge status={data.enrichment_status} />}
        </div>
        <p className="mt-2 text-xs text-[var(--fg-subtle)]">
          Retrieved {new Date(data.retrieved_at).toLocaleString()}
          {data.last_verified_at && ` · Last verified ${new Date(data.last_verified_at).toLocaleString()}`}
        </p>
        {data.source_url && (
          <a
            href={data.source_url}
            target="_blank"
            rel="noreferrer"
            className="mt-1 block text-xs text-[var(--fg-muted)] hover:underline"
          >
            View source →
          </a>
        )}
      </CardContent>
    </Card>
  );
}
