"use client";

import Link from "next/link";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { SeverityBadge } from "@/components/severity-badge";
import { StatusBadge } from "@/components/status-badge";
import { CreatePanel } from "@/components/create-panel";
import { EmptyState } from "@/components/empty-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { CARD_LINK_FOCUS } from "@/lib/focus";
import { apiFetch } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import type {
  EvidenceRequest,
  TrustCenterCategory,
  TrustCenterItem,
  TrustCenterItemStatus,
  Vendor,
} from "@/lib/types";

const selectClassName =
  "flex h-9 rounded-md border border-[var(--border-strong)] bg-[var(--bg-surface)] px-3 py-1 text-sm text-[var(--fg-default)] shadow-[var(--shadow-token-sm)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--border-focus)]";

/* Third parties, and what you publish to your own customers about
 * how you handle their data. */

const TRUST_CENTER_CATEGORIES: TrustCenterCategory[] = [
  "security_overview",
  "privacy_overview",
  "subprocessors",
  "data_locations",
  "encryption_practices",
  "availability",
  "vulnerability_reporting",
  "compliance_roadmap",
  "dpa_availability",
  "incident_communication",
  "responsible_ai",
  "ai_provider_disclosures",
  "retention_deletion",
  "business_continuity",
];

/** The two statuses that assert an outside party's conclusion rather than
 * our own work. Mirrors ATTESTED_STATUSES on the API, which enforces it —
 * this only decides whether to show the attestation fields. */
const ATTESTED_STATUSES = new Set<TrustCenterItemStatus>([
  "independently_assessed",
  "certified",
]);

export function VendorsSection() {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [category, setCategory] = useState("");

  const { data: vendors } = useQuery<Vendor[]>({
    queryKey: ["compliance", "vendors"],
    queryFn: () => apiFetch<Vendor[]>("/api/v1/compliance/vendors"),
  });

  const createVendor = useMutation({
    mutationFn: () =>
      apiFetch<Vendor>("/api/v1/compliance/vendors", {
        method: "POST",
        body: { name, category: category.trim() || "general" },
      }),
    onSuccess: () => {
      setName("");
      setCategory("");
      queryClient.invalidateQueries({ queryKey: ["compliance", "vendors"] });
    },
  });

  return (
    <div className="mb-8">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
        Vendors
      </h2>
      <CreatePanel label="Add vendor">
        <div className="flex flex-wrap gap-2">
          <Input
            placeholder="Vendor name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="min-w-[200px] flex-1"
          />
          <Input
            placeholder="Category (e.g. cloud_infrastructure)"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            className="min-w-[200px] flex-1"
          />
          <Button disabled={!name.trim() || createVendor.isPending} onClick={() => createVendor.mutate()}>
            Add vendor
          </Button>
        </div>
      </CreatePanel>
      {vendors?.length === 0 && <EmptyState
          title="No vendors recorded"
          description={"Record the third parties that process data on your behalf. Their security posture forms part of yours, and enterprise buyers ask about it."}
        />}
      <div className="flex flex-col gap-2">
        {vendors?.map((vendor) => (
          <Link key={vendor.id} href={`/compliance/vendors/${vendor.id}`} className={CARD_LINK_FOCUS}>
            <Card className="transition-colors hover:border-[var(--border-strong)]">
              <CardContent className="flex items-center justify-between pt-6">
                <div>
                  <div className="font-medium text-[var(--fg-default)]">{vendor.name}</div>
                  <div className="text-xs text-[var(--fg-subtle)]">{vendor.category}</div>
                </div>
                <div className="flex items-center gap-2">
                  <SeverityBadge severity={vendor.risk_tier} />
                  <StatusBadge status={vendor.status} />
                </div>
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}

export function TrustCenterSection() {
  const queryClient = useQueryClient();
  const [category, setCategory] = useState<TrustCenterCategory>("security_overview");
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [itemStatus, setItemStatus] = useState<TrustCenterItemStatus>("planned");
  const [isPublic, setIsPublic] = useState(false);
  const [attestationFileId, setAttestationFileId] = useState("");
  const [attestationNote, setAttestationNote] = useState("");

  const { data: items } = useQuery<TrustCenterItem[]>({
    queryKey: ["compliance", "trust-center-items"],
    queryFn: () => apiFetch<TrustCenterItem[]>("/api/v1/trust-center/items"),
  });

  const { data: evidenceRequests } = useQuery<EvidenceRequest[]>({
    queryKey: ["compliance", "trust-center-evidence-requests"],
    queryFn: () => apiFetch<EvidenceRequest[]>("/api/v1/trust-center/evidence-requests"),
  });

  const saveItem = useMutation({
    mutationFn: () =>
      apiFetch<TrustCenterItem>("/api/v1/trust-center/items", {
        method: "POST",
        body: {
          category,
          title,
          content: content.trim() || null,
          status: itemStatus,
          is_public: isPublic,
          attestation_file_id: attestationFileId.trim() || null,
          attestation_note: attestationNote.trim() || null,
        },
      }),
    onSuccess: () => {
      setTitle("");
      setContent("");
      setItemStatus("planned");
      setIsPublic(false);
      setAttestationFileId("");
      setAttestationNote("");
      queryClient.invalidateQueries({ queryKey: ["compliance", "trust-center-items"] });
    },
  });

  const fulfillRequest = useMutation({
    mutationFn: (requestId: string) =>
      apiFetch(`/api/v1/trust-center/evidence-requests/${requestId}/status`, {
        method: "PATCH",
        body: { status: "fulfilled" },
      }),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["compliance", "trust-center-evidence-requests"] }),
  });

  return (
    <div className="mb-8">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
        Trust Center
      </h2>
      <Card className="mb-4">
        <CardContent className="flex flex-col gap-2 pt-6">
          <div className="flex flex-wrap gap-2">
            <select
              className={selectClassName}
              value={category}
              onChange={(e) => setCategory(e.target.value as TrustCenterCategory)}
            >
              {TRUST_CENTER_CATEGORIES.map((c) => (
                <option key={c} value={c}>
                  {c.replace(/_/g, " ")}
                </option>
              ))}
            </select>
            <Input
              placeholder="Title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="min-w-[200px] flex-1"
            />
            <select
              className={selectClassName}
              value={itemStatus}
              onChange={(e) => setItemStatus(e.target.value as TrustCenterItemStatus)}
            >
              <option value="planned">Planned</option>
              <option value="in_progress">In progress</option>
              <option value="implemented">Implemented</option>
              <option value="independently_assessed">Independently assessed</option>
              <option value="certified">Certified</option>
            </select>
          </div>
          <Input
            placeholder="Content (public-facing description)"
            value={content}
            onChange={(e) => setContent(e.target.value)}
          />
          <label className="flex items-center gap-2 text-sm text-[var(--fg-muted)]">
            <input
              type="checkbox"
              checked={isPublic}
              onChange={(e) => setIsPublic(e.target.checked)}
            />
            Publish on public Trust Center page
          </label>

          {/* "Independently assessed" and "certified" state what an
              outside party concluded — the only claims on a trust page a
              buyer cannot check against the rest of it. The API refuses
              them without an attestation, so the form has to collect one
              rather than leaving the reader with a 422 and no way to
              comply. */}
          {ATTESTED_STATUSES.has(itemStatus) && (
            <div className="flex flex-col gap-2 rounded-[var(--radius-md)] border border-[var(--warning-500)]/35 bg-[var(--warning-50)] p-3">
              <p className="text-xs font-semibold uppercase tracking-wide text-[var(--warning-700)]">
                Attestation required
              </p>
              <p className="text-sm leading-relaxed text-[var(--warning-700)]">
                This status says an external party assessed your organization. It cannot be
                inferred from the controls recorded here, so attach the certificate or audit
                report and say what it covers.
              </p>
              <Input
                placeholder="Attestation document file ID"
                value={attestationFileId}
                onChange={(e) => setAttestationFileId(e.target.value)}
              />
              <Input
                placeholder="Who issued it and what it covers (e.g. scope, audit period)"
                value={attestationNote}
                onChange={(e) => setAttestationNote(e.target.value)}
              />
            </div>
          )}

          {saveItem.isError && (
            <p className="text-sm text-[var(--critical-600)]">
              {(saveItem.error as Error).message}
            </p>
          )}

          <Button
            disabled={!title.trim() || saveItem.isPending}
            onClick={() => saveItem.mutate()}
            className="w-fit"
          >
            Save item
          </Button>
        </CardContent>
      </Card>
      {items?.length === 0 && (
        <p className="mb-4 text-sm text-[var(--fg-muted)]">No Trust Center items configured yet.</p>
      )}
      <div className="mb-6 flex flex-col gap-2">
        {items?.map((item) => (
          <Card key={item.id}>
            <CardContent className="flex items-center justify-between pt-6">
              <div>
                <div className="font-medium text-[var(--fg-default)]">{item.title}</div>
                <div className="text-xs text-[var(--fg-subtle)]">{item.category.replace(/_/g, " ")}</div>
              </div>
              <div className="flex items-center gap-2">
                <Badge variant={item.is_public ? "success" : "outline"}>
                  {item.is_public ? "public" : "private"}
                </Badge>
                <StatusBadge status={item.status} />
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
        Evidence Requests
      </h3>
      {evidenceRequests?.length === 0 && (
        <p className="text-sm text-[var(--fg-muted)]">No evidence requests yet.</p>
      )}
      <div className="flex flex-col gap-2">
        {evidenceRequests?.map((request) => (
          <Card key={request.id}>
            <CardContent className="flex items-center justify-between pt-6">
              <div>
                <div className="font-medium text-[var(--fg-default)]">
                  {request.requester_name}
                  {request.company_name ? ` (${request.company_name})` : ""}
                </div>
                <div className="text-xs text-[var(--fg-subtle)]">{request.requester_email}</div>
                {request.message && (
                  <div className="text-sm text-[var(--fg-muted)]">{request.message}</div>
                )}
              </div>
              <div className="flex items-center gap-2">
                <StatusBadge status={request.status} />
                {request.status === "open" && (
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={fulfillRequest.isPending}
                    onClick={() => fulfillRequest.mutate(request.id)}
                  >
                    Mark fulfilled
                  </Button>
                )}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
