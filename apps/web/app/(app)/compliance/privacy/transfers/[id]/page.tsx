"use client";

import Link from "next/link";
import { use } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ArrowRight } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { Card, CardContent } from "@/components/ui/card";
import { apiFetch } from "@/lib/api";
import type { DataTransferDetail, DataTransferStatus } from "@/lib/types";

const selectClassName =
  "flex h-9 rounded-md border border-[var(--border-strong)] bg-white px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--border-focus)]";

const MECHANISM_LABELS: Record<string, string> = {
  adequacy_decision: "Adequacy decision",
  sccs: "Standard contractual clauses",
  bcrs: "Binding corporate rules",
  derogation: "Derogation (Article 49)",
};

/** What the DPA status means for this transfer, rather than what the
 * column says. "Pending" is only a problem where the mechanism actually
 * rests on the contract. */
const DPA_LABELS: Record<string, string> = {
  signed: "Signed",
  pending: "Not signed yet",
  not_required: "Recorded as not required",
};

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-[var(--border-default)] py-2 last:border-0">
      <span className="text-sm text-[var(--fg-muted)]">{label}</span>
      <span className="text-sm text-[var(--fg-default)]">{children}</span>
    </div>
  );
}

/** One transfer, and the records it was assessed against.
 *
 * The review centre and the privacy overview have linked here for a
 * while; until now the link 404'd. What a reviewer needs on arriving is
 * not a form — it is the two claims side by side. The transfer says the
 * data goes to one country under one mechanism; the vendor record says
 * where the vendor is and whether the contract behind that mechanism is
 * signed. Where those disagree the page says so and changes nothing.
 */
export default function DataTransferDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const queryClient = useQueryClient();

  const { data: transfer } = useQuery<DataTransferDetail>({
    queryKey: ["compliance", "data-transfers", id],
    queryFn: () => apiFetch<DataTransferDetail>(`/api/v1/compliance/data-transfers/${id}`),
  });

  const updateStatus = useMutation({
    mutationFn: (status: DataTransferStatus) =>
      apiFetch(`/api/v1/compliance/data-transfers/${id}/status`, {
        method: "PATCH",
        body: { status },
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["compliance"] }),
  });

  if (!transfer) return null;

  const mechanism =
    MECHANISM_LABELS[transfer.transfer_mechanism] ??
    transfer.transfer_mechanism.replace(/_/g, " ");
  // Only relevant where the mechanism rests on the contract. Flagging a
  // missing DPA under an adequacy decision would be noise.
  const dpaMatters = transfer.transfer_mechanism === "sccs";

  return (
    <div>
      <PageHeader
        title={transfer.recipient_name}
        description="International transfer — GDPR Chapter V."
        actions={<StatusBadge status={transfer.status} />}
      />

      {transfer.review_reason && (
        <Card className="mb-6 border-[var(--warning-300)] bg-[var(--warning-50)]">
          <CardContent className="flex gap-3 pt-6">
            <AlertTriangle
              className="mt-0.5 h-5 w-5 shrink-0 text-[var(--warning-600)]"
              aria-hidden="true"
            />
            <div>
              <h2 className="font-medium text-[var(--fg-default)]">Worth another look</h2>
              <p className="mt-1 text-sm leading-relaxed text-[var(--fg-muted)]">
                {transfer.review_reason}
              </p>
              <p className="mt-2 text-sm leading-relaxed text-[var(--fg-muted)]">
                Nothing below has been changed. This transfer still records the
                assessment it was approved with — reassessing it against the new
                facts is your decision to make.
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      <Card className="mb-6">
        <CardContent className="pt-6">
          <h2 className="mb-3 font-medium text-[var(--fg-default)]">The transfer</h2>
          <div className="mb-4 flex flex-wrap items-center gap-2 text-sm">
            <span className="rounded-[var(--radius-md)] border border-[var(--border-default)] px-2 py-1 text-[var(--fg-default)]">
              {transfer.exporter_name}
            </span>
            <ArrowRight className="h-4 w-4 text-[var(--fg-subtle)]" aria-hidden="true" />
            <span className="rounded-[var(--radius-md)] border border-[var(--border-default)] px-2 py-1 text-[var(--fg-default)]">
              {transfer.recipient_name} · {transfer.destination_country}
            </span>
          </div>

          <Row label="Mechanism">{mechanism}</Row>
          <Row label="Processing activity">
            {transfer.processing_activity_name ?? (
              // Not a link: activities have no detail page, and a link
              // that 404s is worse than plain text.
              <span className="text-[var(--fg-subtle)]">Not linked</span>
            )}
          </Row>
          <Row label="Last reviewed">
            {transfer.last_reviewed_at ? (
              new Date(transfer.last_reviewed_at).toLocaleDateString()
            ) : (
              // Recording a mechanism once is not the same claim as the
              // transfer still being covered.
              <span className="text-[var(--fg-subtle)]">Never</span>
            )}
          </Row>
          {transfer.detected_from && (
            <Row label="Detected from">
              <span className="text-[var(--fg-muted)]">{transfer.detected_from}</span>
            </Row>
          )}
        </CardContent>
      </Card>

      <Card className="mb-6">
        <CardContent className="pt-6">
          <h2 className="mb-1 font-medium text-[var(--fg-default)]">Safeguards</h2>
          <p className="mb-3 text-sm text-[var(--fg-muted)]">
            What makes this transfer lawful, as recorded.
          </p>
          {transfer.safeguards_description ? (
            <p className="text-sm leading-relaxed text-[var(--fg-default)]">
              {transfer.safeguards_description}
            </p>
          ) : (
            <p className="rounded-[var(--radius-md)] border border-[var(--border-default)] bg-[var(--bg-app)] p-3 text-sm text-[var(--fg-muted)]">
              No safeguards are described. A mechanism named without safeguards
              recorded is a claim nobody can check.
            </p>
          )}
        </CardContent>
      </Card>

      {transfer.vendor_id && (
        <Card className="mb-6">
          <CardContent className="pt-6">
            <h2 className="mb-1 font-medium text-[var(--fg-default)]">
              What the vendor record says
            </h2>
            <p className="mb-3 text-sm text-[var(--fg-muted)]">
              Shown as the vendor records it, not merged into the transfer above —
              so a disagreement between the two is visible.
            </p>
            <Row label="Vendor">
              <Link
                className="text-[var(--accent-600)] hover:underline"
                href={`/compliance/vendors/${transfer.vendor_id}`}
              >
                {transfer.vendor_name}
              </Link>
            </Row>
            <Row label="Recorded location">
              {transfer.vendor_country ?? (
                <span className="text-[var(--fg-subtle)]">Not recorded</span>
              )}
            </Row>
            <Row label="Data processing agreement">
              {transfer.vendor_dpa_status ? (
                <span
                  className={
                    dpaMatters && transfer.vendor_dpa_status === "pending"
                      ? "text-[var(--warning-600)]"
                      : undefined
                  }
                >
                  {DPA_LABELS[transfer.vendor_dpa_status] ?? transfer.vendor_dpa_status}
                </span>
              ) : (
                <span className="text-[var(--fg-subtle)]">Not recorded</span>
              )}
            </Row>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardContent className="pt-6">
          <h2 className="mb-3 font-medium text-[var(--fg-default)]">Status</h2>
          <select
            className={selectClassName}
            value={transfer.status}
            onChange={(event) =>
              updateStatus.mutate(event.target.value as DataTransferStatus)
            }
          >
            <option value="active">Active</option>
            <option value="under_review">Under review</option>
            <option value="terminated">Terminated</option>
          </select>
        </CardContent>
      </Card>
    </div>
  );
}
