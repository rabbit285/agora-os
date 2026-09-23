"use client";

import Link from "next/link";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle } from "lucide-react";

import { StatusBadge } from "@/components/status-badge";
import { CreatePanel } from "@/components/create-panel";
import { PrivacySuggestions } from "@/components/compliance/privacy-suggestions";
import { StartDpiaScreening } from "@/components/compliance/dpia-screening";
import { EmptyState } from "@/components/empty-state";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { CARD_LINK_FOCUS } from "@/lib/focus";
import { apiFetch } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import type {
  DataTransfer,
  DataTransferStatus,
  DPIA,
  DSAR,
  DSARRequestType,
  LegalBasis,
  ProcessingActivity,
  TransferMechanism,
} from "@/lib/types";

const selectClassName =
  "flex h-9 rounded-md border border-[var(--border-strong)] bg-[var(--bg-surface)] px-3 py-1 text-sm text-[var(--fg-default)] shadow-[var(--shadow-token-sm)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--border-focus)]";

/* The privacy operations a data protection officer actually runs:
 * what you process, the assessments that gate it, the requests people
 * make about their own data, and where that data goes. */

const LEGAL_BASIS_OPTIONS: { value: LegalBasis; label: string }[] = [
  { value: "consent", label: "Consent" },
  { value: "contract", label: "Contract" },
  { value: "legal_obligation", label: "Legal obligation" },
  { value: "vital_interests", label: "Vital interests" },
  { value: "public_task", label: "Public task" },
  { value: "legitimate_interests", label: "Legitimate interests" },
];

/** A row of filters over a list. Small, shared, and the same shape on
 * every privacy list so the lists behave alike. */
function FilterBar({
  value,
  onChange,
  options,
}: {
  value: string;
  onChange: (next: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <div className="mb-3 flex flex-wrap gap-1.5">
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          aria-pressed={value === option.value}
          onClick={() => onChange(option.value)}
          className={`rounded-full border px-2.5 py-1 text-xs transition-colors ${
            value === option.value
              ? "border-[var(--border-strong)] bg-[var(--bg-subtle)] font-medium text-[var(--fg-default)]"
              : "border-[var(--border-default)] text-[var(--fg-muted)] hover:text-[var(--fg-default)]"
          }`}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

export function ProcessingActivitiesSection() {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [purpose, setPurpose] = useState("");
  // Empty until somebody chooses. A pre-selected lawful basis is an
  // answer nobody gave, and "Legitimate interests" is the worst one to
  // give by default: it is the basis that requires a balancing test.
  const [legalBasis, setLegalBasis] = useState<LegalBasis | "">("");
  const [dataSubjects, setDataSubjects] = useState("");
  const [retentionPeriod, setRetentionPeriod] = useState("");

  const { data: activities } = useQuery<ProcessingActivity[]>({
    queryKey: ["compliance", "processing-activities"],
    queryFn: () => apiFetch<ProcessingActivity[]>("/api/v1/compliance/processing-activities"),
  });

  const createActivity = useMutation({
    mutationFn: () =>
      apiFetch<ProcessingActivity>("/api/v1/compliance/processing-activities", {
        method: "POST",
        body: {
          name,
          purpose,
          legal_basis: legalBasis,
          data_subjects: dataSubjects,
          retention_period: retentionPeriod,
        },
      }),
    onSuccess: () => {
      setName("");
      setPurpose("");
      setDataSubjects("");
      setRetentionPeriod("");
      queryClient.invalidateQueries({ queryKey: ["compliance", "processing-activities"] });
    },
  });

  const canCreate =
    name.trim() &&
    purpose.trim() &&
    dataSubjects.trim() &&
    retentionPeriod.trim() &&
    // A lawful basis is not optional and is not guessable. Without one
    // this is not a RoPA entry.
    legalBasis;

  return (
    <div className="mb-8">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
        Record of Processing Activities (RoPA)
      </h2>
      {/* Drafted from AI systems and vendors already on file, so the
          same facts are not typed twice. */}
      <PrivacySuggestions kind="processing_activity" />
      <CreatePanel label="Add manually">
        <div className="flex flex-wrap gap-2">
          <Input
            placeholder="Activity name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="min-w-[180px] flex-1"
          />
          <Input
            placeholder="Purpose"
            value={purpose}
            onChange={(e) => setPurpose(e.target.value)}
            className="min-w-[180px] flex-1"
          />
          <select
            className={selectClassName}
            value={legalBasis}
            onChange={(e) => setLegalBasis(e.target.value as LegalBasis)}
          >
            <option value="">Select lawful basis…</option>
            {LEGAL_BASIS_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
          <Input
            placeholder="Data subjects (e.g. customers)"
            value={dataSubjects}
            onChange={(e) => setDataSubjects(e.target.value)}
            className="min-w-[180px] flex-1"
          />
          <Input
            placeholder="Retention period"
            value={retentionPeriod}
            onChange={(e) => setRetentionPeriod(e.target.value)}
            className="min-w-[180px] flex-1"
          />
          <Button disabled={!canCreate || createActivity.isPending} onClick={() => createActivity.mutate()}>
            Add activity
          </Button>
        </div>
      </CreatePanel>
      {activities?.length === 0 && (
        <EmptyState
          title="No processing activities recorded"
          description={"A record of processing activities is what GDPR Article 30 asks for: for each activity, why you process the data, whose it is, who receives it and how long you keep it."}
        />
      )}
      <div className="flex flex-col gap-2">
        {activities?.map((activity) => (
          <Card key={activity.id}>
            <CardContent className="flex items-center justify-between pt-6">
              <div>
                <div className="font-medium text-[var(--fg-default)]">{activity.name}</div>
                <div className="text-xs text-[var(--fg-subtle)]">
                  {activity.legal_basis.replace(/_/g, " ")} · {activity.data_subjects}
                </div>
              </div>
              <StatusBadge status={activity.status} />
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

/** The lifecycle in the words a reader uses, not the column values.
 *
 * `not_required` especially: it was stored as `approved`, so a screening
 * that concluded no assessment was needed read on this list as a DPIA
 * that had been carried out and signed off. */
const DPIA_STATUS_LABELS: Record<string, string> = {
  screening: "Screening",
  not_required: "No DPIA required",
  draft: "Draft",
  in_review: "In review",
  approved: "Approved",
  completed: "Completed",
  rejected: "Rejected",
};

const DPIA_STAGE: Record<string, string> = {
  screening: "Screening · waiting on your decision",
  not_required: "Screening complete · no DPIA required",
  completed: "Assessment complete",
};

export function DPIASection() {
  const { data: dpias } = useQuery<DPIA[]>({
    queryKey: ["compliance", "dpias"],
    queryFn: () => apiFetch<DPIA[]>("/api/v1/compliance/dpias"),
  });

  return (
    <div className="mb-8">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
        Data Protection Impact Assessments (DPIA)
      </h2>
      {/* §4/§19: one action, and it starts with screening rather than
          with a risk level nobody has established yet. */}
      <div className="mb-4">
        <StartDpiaScreening />
      </div>
      {dpias?.length === 0 && (
        <EmptyState
          title="No DPIAs recorded"
          description={"Start from a processing activity or an AI system. Screening records whether an assessment is needed and why — Veyntra counts the criteria you report, and the conclusion is yours."}
        />
      )}
      <div className="flex flex-col gap-2">
        {dpias?.map((dpia) => (
          <Link
            key={dpia.id}
            href={`/compliance/dpias/${dpia.id}`}
            className={CARD_LINK_FOCUS}
          >
            <Card className="transition-colors hover:border-[var(--border-strong)]">
              <CardContent className="flex items-center justify-between pt-6">
                <div>
                  <div className="font-medium text-[var(--fg-default)]">
                    {dpia.title}
                  </div>
                  <div className="text-xs text-[var(--fg-subtle)]">
                    {DPIA_STAGE[dpia.status] ??
                      (dpia.screening_outcome
                        ? `Screened · ${dpia.screening_outcome.replace(/_/g, " ")}`
                        : "Not screened yet")}
                    {dpia.ai_system_id && " · Linked to an AI system"}
                  </div>
                  {/* A completed assessment whose processing has moved
                      on is the one row on this list somebody needs to
                      see without opening it. */}
                  {dpia.review_reason && (
                    <div className="mt-1 text-xs text-[var(--warning-700)]">
                      Reassessment recommended — the processing has changed
                      since this was completed.
                    </div>
                  )}
                </div>
                <StatusBadge
                  status={dpia.status}
                  label={DPIA_STATUS_LABELS[dpia.status]}
                />
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}

export function DSARSection() {
  const queryClient = useQueryClient();
  const [requesterName, setRequesterName] = useState("");
  const [requesterEmail, setRequesterEmail] = useState("");
  const [requestType, setRequestType] = useState<DSARRequestType>("access");
  // Defaults to today, but it is a field rather than an assumption: the
  // response clock runs from receipt, and a request entered three days
  // late does not get three extra days.
  const [receivedAt, setReceivedAt] = useState(
    () => new Date().toISOString().slice(0, 10),
  );
  const [filter, setFilter] = useState("all");

  const { data: dsars } = useQuery<DSAR[]>({
    queryKey: ["compliance", "dsars"],
    queryFn: () => apiFetch<DSAR[]>("/api/v1/compliance/dsars"),
  });

  // Urgency first. A list ordered by when somebody happened to log a
  // request buries the one that is already late behind five that are not.
  const visibleDsars = [...(dsars ?? [])]
    .filter((dsar) => {
      const open = dsar.status !== "fulfilled" && dsar.status !== "rejected";
      switch (filter) {
        case "open":
          return open;
        case "due_soon":
          return dsar.due_soon;
        case "overdue":
          return dsar.overdue;
        case "identity":
          return open && dsar.verification_status === "pending";
        default:
          return true;
      }
    })
    .sort((a, b) => {
      const rank = (dsar: DSAR) =>
        dsar.overdue ? 0 : dsar.due_soon ? 1 : dsar.fulfilled_at ? 3 : 2;
      return rank(a) - rank(b) || a.due_at.localeCompare(b.due_at);
    });

  const createDsar = useMutation({
    mutationFn: () =>
      apiFetch<DSAR>("/api/v1/compliance/dsars", {
        method: "POST",
        body: {
          requester_name: requesterName,
          requester_email: requesterEmail,
          // Receipt, not entry. The deadline is calculated from this.
          received_at: receivedAt ? new Date(receivedAt).toISOString() : undefined,
          request_type: requestType,
        },
      }),
    onSuccess: () => {
      setRequesterName("");
      setRequesterEmail("");
      queryClient.invalidateQueries({ queryKey: ["compliance", "dsars"] });
    },
  });

  return (
    <div className="mb-8">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
        Data Subject Access Requests (DSAR)
      </h2>
      <CreatePanel label="Log a request">
        <div className="flex flex-wrap gap-2">
          <Input
            placeholder="Requester name"
            value={requesterName}
            onChange={(e) => setRequesterName(e.target.value)}
            className="min-w-[180px] flex-1"
          />
          <label
            className="text-xs text-[var(--fg-muted)]"
            htmlFor="dsar-received"
          >
            When the request was received
          </label>
          <Input
            id="dsar-received"
            type="date"
            value={receivedAt}
            max={new Date().toISOString().slice(0, 10)}
            onChange={(e) => setReceivedAt(e.target.value)}
            className="w-48"
          />
          <p className="text-xs text-[var(--fg-subtle)]">
            The response clock runs from receipt, not from when it was
            entered here — a request logged three days late does not get
            three extra days.
          </p>
          <Input
            placeholder="Requester email"
            value={requesterEmail}
            onChange={(e) => setRequesterEmail(e.target.value)}
            className="min-w-[180px] flex-1"
          />
          <select
            className={selectClassName}
            value={requestType}
            onChange={(e) => setRequestType(e.target.value as DSARRequestType)}
          >
            <option value="access">Access</option>
            <option value="deletion">Deletion</option>
            <option value="rectification">Rectification</option>
            <option value="portability">Portability</option>
          </select>
          <Button
            disabled={!requesterName.trim() || !requesterEmail.trim() || createDsar.isPending}
            onClick={() => createDsar.mutate()}
          >
            Log DSAR
          </Button>
        </div>
        <div className="pt-0 pb-4">
          <p className="text-xs text-[var(--fg-subtle)]">
            {/* One month, not thirty days. A request received on 31
                January is due on 28 February; the two dates differ for
                most of the year, and the deadline is calculated from the
                date of receipt rather than assumed. */}
            Response due within one month of receipt. The deadline is
            calculated from the date the request was received.
          </p>
        </div>
      </CreatePanel>
      {dsars?.length === 0 && <EmptyState
          title="No open data requests"
          description={"New privacy requests will appear here. Log one when somebody asks for access to, correction of, or deletion of their personal data — the response clock is one month from receipt."}
        />}

      {(dsars?.length ?? 0) > 0 && (
        <FilterBar
          value={filter}
          onChange={setFilter}
          options={[
            { value: "all", label: `All (${dsars?.length ?? 0})` },
            { value: "open", label: "Open" },
            { value: "due_soon", label: "Due soon" },
            { value: "overdue", label: "Overdue" },
            { value: "identity", label: "Identity pending" },
          ]}
        />
      )}

      <div className="flex flex-col gap-2">
        {visibleDsars.map((dsar) => (
          <Link key={dsar.id} href={`/compliance/dsars/${dsar.id}`} className={CARD_LINK_FOCUS}>
            <Card className="transition-colors hover:border-[var(--border-strong)]">
              <CardContent className="flex items-center justify-between pt-6">
                <div>
                  <div className="font-medium text-[var(--fg-default)]">{dsar.requester_name}</div>
                  <div className="text-xs text-[var(--fg-subtle)]">
                    {dsar.request_type} · due{" "}
                    {new Date(dsar.due_at).toLocaleDateString()}
                    {dsar.extension_months > 0 && " (extended)"}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {/* The deadline is the thing a person is judged on, so
                      it reads as words rather than a date to subtract
                      today from. */}
                  {dsar.deadline_label && (
                    <span
                      className={`text-xs ${
                        dsar.overdue
                          ? "font-semibold text-[var(--fg-danger)]"
                          : dsar.due_soon
                            ? "font-medium text-[var(--warning-700)]"
                            : "text-[var(--fg-subtle)]"
                      }`}
                    >
                      {dsar.deadline_label}
                    </span>
                  )}
                  <StatusBadge status={dsar.status} />
                </div>
              </CardContent>
            </Card>
          </Link>
        ))}
        {visibleDsars.length === 0 && (dsars?.length ?? 0) > 0 && (
          <p className="px-1 py-3 text-sm text-[var(--fg-muted)]">
            No requests match this filter.
          </p>
        )}
      </div>
    </div>
  );
}

export function DataTransfersSection() {
  const queryClient = useQueryClient();
  const [recipientName, setRecipientName] = useState("");
  const [destinationCountry, setDestinationCountry] = useState("");
  // Which mechanism covers a transfer is a legal judgement. The form
  // asks; it does not answer.
  const [transferMechanism, setTransferMechanism] = useState<
    TransferMechanism | ""
  >("");

  const { data: transfers } = useQuery<DataTransfer[]>({
    queryKey: ["compliance", "data-transfers"],
    queryFn: () => apiFetch<DataTransfer[]>("/api/v1/compliance/data-transfers"),
  });

  const createTransfer = useMutation({
    mutationFn: () =>
      apiFetch<DataTransfer>("/api/v1/compliance/data-transfers", {
        method: "POST",
        body: {
          recipient_name: recipientName,
          destination_country: destinationCountry.toUpperCase(),
          transfer_mechanism: transferMechanism,
        },
      }),
    onSuccess: () => {
      setRecipientName("");
      setDestinationCountry("");
      setTransferMechanism("");
      queryClient.invalidateQueries({ queryKey: ["compliance", "data-transfers"] });
      queryClient.invalidateQueries({ queryKey: ["compliance", "risks"] });
    },
  });

  const updateStatus = useMutation({
    mutationFn: ({ id, status: newStatus }: { id: string; status: DataTransferStatus }) =>
      apiFetch(`/api/v1/compliance/data-transfers/${id}/status`, {
        method: "PATCH",
        body: { status: newStatus },
      }),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["compliance", "data-transfers"] }),
  });

  return (
    <div className="mb-8">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
        Data Transfers
      </h2>
      {/* Detected from processing activities whose processor is outside
          the EEA. The mechanism stays the reviewer's call. */}
      <PrivacySuggestions kind="transfer" />
      <CreatePanel label="Add manually">
        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap gap-2">
            <Input
              placeholder="Recipient name"
              value={recipientName}
              onChange={(e) => setRecipientName(e.target.value)}
              className="min-w-[200px] flex-1"
            />
            <Input
              placeholder="Destination country (e.g. US)"
              value={destinationCountry}
              onChange={(e) => setDestinationCountry(e.target.value)}
              maxLength={2}
              className="w-40"
            />
            <select
              className={selectClassName}
              value={transferMechanism}
              onChange={(e) => setTransferMechanism(e.target.value as TransferMechanism)}
            >
              <option value="">Select transfer mechanism…</option>
              <option value="adequacy_decision">Adequacy decision</option>
              <option value="sccs">Standard Contractual Clauses</option>
              <option value="bcrs">Binding Corporate Rules</option>
              <option value="derogation">Article 49 derogation</option>
            </select>
            <Button
              disabled={
                !recipientName.trim() ||
                destinationCountry.trim().length !== 2 ||
                // Which mechanism covers a transfer is the reviewer's
                // call, so the form will not submit without one.
                !transferMechanism ||
                createTransfer.isPending
              }
              onClick={() => createTransfer.mutate()}
            >
              Log transfer
            </Button>
          </div>
          <p className="text-xs text-[var(--fg-subtle)]">
            A transfer relying on an Article 49 derogation automatically creates a linked Risk
            in the Risk Register.
          </p>
        </div>
      </CreatePanel>
      {transfers?.length === 0 && (
        <EmptyState
          title="No international transfers recorded"
          description={"Record where personal data leaves its home jurisdiction and what makes that lawful — adequacy, standard contractual clauses, or a derogation."}
        />
      )}
      <div className="flex flex-col gap-2">
        {transfers?.map((transfer) => (
          <Card key={transfer.id}>
            <CardContent className="pt-6">
              <div className="flex items-center justify-between">
              <div>
                <div className="font-medium text-[var(--fg-default)]">{transfer.recipient_name}</div>
                <div className="text-xs text-[var(--fg-subtle)]">
                  {transfer.destination_country} · {transfer.transfer_mechanism.replace(/_/g, " ")}
                </div>
                {transfer.detected_from && (
                  <div className="text-xs text-[var(--fg-subtle)]">
                    Detected from {transfer.detected_from}
                  </div>
                )}
                {transfer.related_risk_id && (
                  <div className="text-xs text-[var(--critical-600)]">Linked risk created</div>
                )}
              </div>
              <div className="flex items-center gap-2">
                <select
                  className={selectClassName}
                  value={transfer.status}
                  onChange={(e) =>
                    updateStatus.mutate({
                      id: transfer.id,
                      status: e.target.value as DataTransferStatus,
                    })
                  }
                >
                  <option value="active">Active</option>
                  <option value="under_review">Under review</option>
                  <option value="terminated">Terminated</option>
                </select>
                <StatusBadge status={transfer.status} />
              </div>
              </div>

              {/* A fact underneath this transfer moved. Said here rather
                  than applied: the record still says what the person who
                  approved it decided, and re-approving is their call. */}
              {transfer.review_reason && (
                <div className="mt-3 flex gap-2 rounded-[var(--radius-md)] border border-[var(--warning-300)] bg-[var(--warning-50)] p-3">
                  <AlertTriangle
                    className="mt-0.5 h-4 w-4 shrink-0 text-[var(--warning-600)]"
                    aria-hidden="true"
                  />
                  <div>
                    <div className="text-xs font-medium text-[var(--fg-default)]">
                      Worth another look
                    </div>
                    <p className="mt-0.5 text-xs leading-relaxed text-[var(--fg-muted)]">
                      {transfer.review_reason} This record has not been changed.
                    </p>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
