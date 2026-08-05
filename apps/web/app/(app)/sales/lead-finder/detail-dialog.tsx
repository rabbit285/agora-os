"use client";

import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { NormalizedCompanyOut, NormalizedPersonOut } from "@/lib/types";

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  if (value === null || value === undefined || value === "") return null;
  return (
    <div>
      <dt className="text-[11px] uppercase tracking-wide text-[var(--fg-subtle)]">{label}</dt>
      <dd className="text-sm text-[var(--fg-default)]">{value}</dd>
    </div>
  );
}

export function CompanyDetailDialog({
  company,
  onOpenChange,
  onSave,
  saving,
}: {
  company: NormalizedCompanyOut | null;
  onOpenChange: (open: boolean) => void;
  onSave: (company: NormalizedCompanyOut) => void;
  saving: boolean;
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
              <p className="mb-1 text-[11px] uppercase tracking-wide text-[var(--fg-subtle)]">
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
          <p className="text-[11px] text-[var(--fg-subtle)]">
            Source: {company.provider} · retrieved {new Date(company.retrieved_at).toLocaleString()}
          </p>
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
          <p className="text-[11px] text-[var(--fg-subtle)]">
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
