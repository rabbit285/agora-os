"use client";

import Link from "next/link";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { StatusBadge } from "@/components/status-badge";
import { CreatePanel } from "@/components/create-panel";
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
  DPIARiskLevel,
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
  const [legalBasis, setLegalBasis] = useState<LegalBasis>("legitimate_interests");
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
    name.trim() && purpose.trim() && dataSubjects.trim() && retentionPeriod.trim();

  return (
    <div className="mb-8">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
        Record of Processing Activities (RoPA)
      </h2>
      <CreatePanel label="Add processing activity">
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

export function DPIASection() {
  const queryClient = useQueryClient();
  const [title, setTitle] = useState("");
  const [riskLevel, setRiskLevel] = useState<DPIARiskLevel>("low");

  const { data: dpias } = useQuery<DPIA[]>({
    queryKey: ["compliance", "dpias"],
    queryFn: () => apiFetch<DPIA[]>("/api/v1/compliance/dpias"),
  });

  const createDpia = useMutation({
    mutationFn: () =>
      apiFetch<DPIA>("/api/v1/compliance/dpias", {
        method: "POST",
        body: { title, risk_level: riskLevel },
      }),
    onSuccess: () => {
      setTitle("");
      setRiskLevel("low");
      queryClient.invalidateQueries({ queryKey: ["compliance", "dpias"] });
    },
  });

  return (
    <div className="mb-8">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
        Data Protection Impact Assessments (DPIA)
      </h2>
      <CreatePanel label="Create DPIA">
        <div className="flex flex-wrap gap-2">
          <Input
            placeholder="DPIA title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="min-w-[200px] flex-1"
          />
          <select
            className={selectClassName}
            value={riskLevel}
            onChange={(e) => setRiskLevel(e.target.value as DPIARiskLevel)}
          >
            <option value="low">Low risk</option>
            <option value="medium">Medium risk</option>
            <option value="high">High risk</option>
          </select>
          <Button disabled={!title.trim() || createDpia.isPending} onClick={() => createDpia.mutate()}>
            Start DPIA
          </Button>
        </div>
        <div className="pt-0 pb-4">
          <p className="text-xs text-[var(--fg-subtle)]">
            A high-risk DPIA automatically requires an Approval before it can be marked approved
            (GDPR Article 35).
          </p>
        </div>
      </CreatePanel>
      {dpias?.length === 0 && <EmptyState
          title="No DPIAs recorded"
          description={"A data protection impact assessment is required where processing is likely to be high risk — profiling, large-scale special category data, or systematic monitoring."}
        />}
      <div className="flex flex-col gap-2">
        {dpias?.map((dpia) => (
          <Link key={dpia.id} href={`/compliance/dpias/${dpia.id}`} className={CARD_LINK_FOCUS}>
            <Card className="transition-colors hover:border-[var(--border-strong)]">
              <CardContent className="flex items-center justify-between pt-6">
                <div>
                  <div className="font-medium text-[var(--fg-default)]">{dpia.title}</div>
                  {dpia.ai_system_id && (
                    <div className="text-xs text-[var(--fg-subtle)]">Linked to an AI system</div>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <StatusBadge status={dpia.risk_level} />
                  <StatusBadge status={dpia.status} />
                </div>
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
  const [transferMechanism, setTransferMechanism] = useState<TransferMechanism>("sccs");

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
      setTransferMechanism("sccs");
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
      <CreatePanel label="Log a transfer">
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
              <option value="adequacy_decision">Adequacy decision</option>
              <option value="sccs">Standard Contractual Clauses</option>
              <option value="bcrs">Binding Corporate Rules</option>
              <option value="derogation">Article 49 derogation</option>
            </select>
            <Button
              disabled={
                !recipientName.trim() ||
                destinationCountry.trim().length !== 2 ||
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
            <CardContent className="flex items-center justify-between pt-6">
              <div>
                <div className="font-medium text-[var(--fg-default)]">{transfer.recipient_name}</div>
                <div className="text-xs text-[var(--fg-subtle)]">
                  {transfer.destination_country} · {transfer.transfer_mechanism.replace(/_/g, " ")}
                </div>
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
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
