"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Users } from "lucide-react";

import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { apiFetch } from "@/lib/api";
import type { NormalizedCompanyOut, NormalizedPersonOut, PersonSearchOut } from "@/lib/types";

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  if (value === null || value === undefined || value === "") return null;
  return (
    <div>
      <dt className="text-[11px] uppercase tracking-wide text-[var(--fg-muted)]">{label}</dt>
      <dd className="text-sm text-[var(--fg-default)]">{value}</dd>
    </div>
  );
}

/** Journey: "find decision-makers" — a company-scoped person search
 * against the same POST /decision-makers the brief specifies, shown
 * inline rather than a full tab switch so the company context stays
 * visible. Results go through the exact same save path as any other
 * person search result. */
function DecisionMakersSection({
  domain,
  onSavePerson,
  saving,
}: {
  domain: string;
  onSavePerson: (person: NormalizedPersonOut) => void;
  saving: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const findDecisionMakers = useMutation({
    mutationFn: () =>
      apiFetch<PersonSearchOut>("/api/v1/sales/lead-finder/decision-makers", {
        method: "POST",
        body: { company_domain: domain },
      }),
  });

  if (!expanded) {
    return (
      <Button
        size="sm"
        variant="outline"
        onClick={() => {
          setExpanded(true);
          findDecisionMakers.mutate();
        }}
      >
        <Users className="h-3.5 w-3.5" />
        Find decision-makers
      </Button>
    );
  }

  return (
    <div className="rounded-[var(--radius-md)] border border-[var(--border-default)] p-3">
      <p className="mb-2 text-[11px] uppercase tracking-wide text-[var(--fg-muted)]">
        Decision-makers
      </p>
      {findDecisionMakers.isPending && (
        <p className="text-xs text-[var(--fg-muted)]">Searching…</p>
      )}
      {findDecisionMakers.data && findDecisionMakers.data.people.length === 0 && (
        <p className="text-xs text-[var(--fg-muted)]">No decision-makers found for this domain.</p>
      )}
      <ul className="flex flex-col gap-2">
        {findDecisionMakers.data?.people.map((person) => (
          <li
            key={person.provider_record_id}
            className="flex items-center justify-between rounded-[var(--radius-sm)] bg-[var(--bg-sunken)] px-2 py-1.5"
          >
            <div>
              <p className="text-sm font-medium">{person.full_name}</p>
              <p className="text-xs text-[var(--fg-muted)]">{person.title}</p>
            </div>
            {person.dedupe_status === "existing" ? (
              <Badge variant="outline">Saved</Badge>
            ) : (
              <Button size="sm" variant="outline" disabled={saving} onClick={() => onSavePerson(person)}>
                Save
              </Button>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function CompanyDetailDialog({
  company,
  onOpenChange,
  onSave,
  saving,
  onSavePerson,
  savingPerson,
}: {
  company: NormalizedCompanyOut | null;
  onOpenChange: (open: boolean) => void;
  onSave: (company: NormalizedCompanyOut) => void;
  saving: boolean;
  onSavePerson: (person: NormalizedPersonOut) => void;
  savingPerson: boolean;
}) {
  return (
    <Dialog open={company !== null} onOpenChange={onOpenChange}>
      {company && (
        <DialogContent className="max-w-xl">
          <DialogHeader>
            <DialogTitle>{company.name}</DialogTitle>
          </DialogHeader>
          <dl className="grid grid-cols-2 gap-3">
            <Field label="Domain" value={company.domain} />
            <Field label="Website" value={company.website} />
            <Field label="Industry" value={company.industry} />
            <Field label="Employees" value={company.employee_count ?? company.employee_range} />
            <Field label="Revenue range" value={company.revenue_range} />
            <Field label="Funding stage" value={company.funding_stage} />
            <Field
              label="Total funding"
              value={company.total_funding_usd ? `$${company.total_funding_usd.toLocaleString()}` : null}
            />
            <Field label="Locations" value={company.locations.join(", ")} />
          </dl>
          {company.technologies.length > 0 && (
            <div>
              <p className="mb-1 text-[11px] uppercase tracking-wide text-[var(--fg-muted)]">
                Technologies
              </p>
              <div className="flex flex-wrap gap-1">
                {company.technologies.map((tech) => (
                  <Badge key={tech} variant="outline">
                    {tech}
                  </Badge>
                ))}
              </div>
            </div>
          )}
          <p className="text-[11px] text-[var(--fg-muted)]">
            Source: {company.provider} · retrieved {new Date(company.retrieved_at).toLocaleString()}
          </p>
          {company.domain && (
            <DecisionMakersSection
              domain={company.domain}
              onSavePerson={onSavePerson}
              saving={savingPerson}
            />
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              Close
            </Button>
            {company.dedupe_status === "existing" ? (
              <Badge variant="outline">Already saved</Badge>
            ) : (
              <Button disabled={saving} onClick={() => onSave(company)}>
                {saving ? "Saving…" : "Save to Accounts"}
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      )}
    </Dialog>
  );
}

export function PersonDetailDialog({
  person,
  onOpenChange,
  onSave,
  saving,
}: {
  person: NormalizedPersonOut | null;
  onOpenChange: (open: boolean) => void;
  onSave: (person: NormalizedPersonOut) => void;
  saving: boolean;
}) {
  return (
    <Dialog open={person !== null} onOpenChange={onOpenChange}>
      {person && (
        <DialogContent className="max-w-xl">
          <DialogHeader>
            <DialogTitle>{person.full_name}</DialogTitle>
          </DialogHeader>
          <dl className="grid grid-cols-2 gap-3">
            <Field label="Title" value={person.title} />
            <Field label="Seniority" value={person.seniority} />
            <Field label="Department" value={person.department} />
            <Field label="Company" value={person.current_company_name ?? person.current_company_domain} />
            <Field label="Location" value={person.location} />
            <Field
              label="Email"
              value={
                person.email ? (
                  <>
                    {person.email} <Badge variant="outline">{person.email_status}</Badge>
                  </>
                ) : (
                  <Badge variant="outline">unavailable</Badge>
                )
              }
            />
            <Field
              label="Phone"
              value={person.phone ? <>{person.phone} <Badge variant="outline">{person.phone_status}</Badge></> : null}
            />
          </dl>
          <p className="text-[11px] text-[var(--fg-muted)]">
            Source: {person.provider} · retrieved {new Date(person.retrieved_at).toLocaleString()}
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              Close
            </Button>
            {person.dedupe_status === "existing" ? (
              <Badge variant="outline">Already saved</Badge>
            ) : (
              <Button disabled={saving} onClick={() => onSave(person)}>
                {saving ? "Saving…" : "Save to Contacts"}
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      )}
    </Dialog>
  );
}
