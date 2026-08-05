"use client";

import { Check, Plus } from "lucide-react";

import { DataTable, type DataTableColumn } from "@/components/data-table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { NormalizedCompanyOut, NormalizedPersonOut } from "@/lib/types";

function DedupeBadge({ status }: { status: "new" | "existing" }) {
  return status === "existing" ? (
    <Badge variant="outline">Existing</Badge>
  ) : (
    <Badge variant="secondary">New</Badge>
  );
}

function SelectCheckbox({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: () => void;
  label: string;
}) {
  return (
    <input
      type="checkbox"
      checked={checked}
      onChange={onChange}
      aria-label={label}
      className="h-3.5 w-3.5 accent-[var(--brand-primary)]"
    />
  );
}

export function CompanyResultsTable({
  companies,
  isLoading,
  error,
  onRetry,
  density,
  selected,
  onToggleSelect,
  onSave,
  savingKey,
  onViewDetail,
}: {
  companies: NormalizedCompanyOut[] | undefined;
  isLoading: boolean;
  error: unknown;
  onRetry: () => void;
  density: "comfortable" | "compact";
  selected: Set<string>;
  onToggleSelect: (id: string) => void;
  onSave: (company: NormalizedCompanyOut) => void;
  savingKey: string | null;
  onViewDetail: (company: NormalizedCompanyOut) => void;
}) {
  const columns: DataTableColumn<NormalizedCompanyOut>[] = [
    {
      key: "select",
      header: "",
      render: (company) => (
        <SelectCheckbox
          checked={selected.has(company.provider_record_id)}
          onChange={() => onToggleSelect(company.provider_record_id)}
          label={`Select ${company.name}`}
        />
      ),
      className: "w-8",
    },
    {
      key: "name",
      header: "Company",
      render: (company) => (
        <div className="flex flex-col">
          <span className="font-medium">{company.name}</span>
          {company.domain && <span className="text-xs text-[var(--fg-subtle)]">{company.domain}</span>}
        </div>
      ),
      sortValue: (company) => company.name.toLowerCase(),
    },
    {
      key: "industry",
      header: "Industry",
      render: (company) => company.industry ?? "—",
      sortValue: (company) => company.industry ?? "",
    },
    {
      key: "employees",
      header: "Employees",
      render: (company) => company.employee_count ?? company.employee_range ?? "—",
      sortValue: (company) => company.employee_count ?? -1,
    },
    {
      key: "location",
      header: "Location",
      render: (company) => company.locations[0] ?? "—",
    },
    {
      key: "funding",
      header: "Funding",
      render: (company) => company.funding_stage ?? "—",
    },
    {
      key: "technologies",
      header: "Technologies",
      render: (company) => (
        <div className="flex flex-wrap gap-1">
          {company.technologies.slice(0, 3).map((tech) => (
            <Badge key={tech} variant="outline">
              {tech}
            </Badge>
          ))}
          {company.technologies.length > 3 && (
            <span className="text-xs text-[var(--fg-subtle)]">+{company.technologies.length - 3}</span>
          )}
        </div>
      ),
    },
    {
      key: "dedupe",
      header: "Status",
      render: (company) => <DedupeBadge status={company.dedupe_status} />,
    },
  ];

  return (
    <DataTable
      columns={columns}
      data={companies}
      getRowId={(company) => company.provider_record_id}
      onRowClick={onViewDetail}
      isLoading={isLoading}
      error={error}
      onRetry={onRetry}
      density={density}
      emptyTitle="No companies match these filters"
      emptyDescription="Adjust the filters or clear them to broaden the search."
      rowActions={(company) =>
        company.dedupe_status === "existing" ? (
          <Badge variant="outline">
            <Check className="h-3 w-3" /> Saved
          </Badge>
        ) : (
          <Button
            size="sm"
            variant="outline"
            disabled={savingKey === company.provider_record_id}
            onClick={() => onSave(company)}
          >
            <Plus className="h-3.5 w-3.5" />
            {savingKey === company.provider_record_id ? "Saving…" : "Save"}
          </Button>
        )
      }
    />
  );
}

function EmailStatusBadge({ status }: { status: NormalizedPersonOut["email_status"] }) {
  const variant = status === "verified" ? "success" : status === "unavailable" ? "outline" : "secondary";
  return <Badge variant={variant}>{status.replace(/_/g, " ")}</Badge>;
}

export function PersonResultsTable({
  people,
  isLoading,
  error,
  onRetry,
  density,
  selected,
  onToggleSelect,
  onSave,
  savingKey,
  onViewDetail,
}: {
  people: NormalizedPersonOut[] | undefined;
  isLoading: boolean;
  error: unknown;
  onRetry: () => void;
  density: "comfortable" | "compact";
  selected: Set<string>;
  onToggleSelect: (id: string) => void;
  onSave: (person: NormalizedPersonOut) => void;
  savingKey: string | null;
  onViewDetail: (person: NormalizedPersonOut) => void;
}) {
  const columns: DataTableColumn<NormalizedPersonOut>[] = [
    {
      key: "select",
      header: "",
      render: (person) => (
        <SelectCheckbox
          checked={selected.has(person.provider_record_id)}
          onChange={() => onToggleSelect(person.provider_record_id)}
          label={`Select ${person.full_name}`}
        />
      ),
      className: "w-8",
    },
    {
      key: "name",
      header: "Name",
      render: (person) => (
        <div className="flex flex-col">
          <span className="font-medium">{person.full_name}</span>
          {person.title && <span className="text-xs text-[var(--fg-subtle)]">{person.title}</span>}
        </div>
      ),
      sortValue: (person) => person.full_name.toLowerCase(),
    },
    {
      key: "company",
      header: "Company",
      render: (person) => person.current_company_name ?? person.current_company_domain ?? "—",
    },
    {
      key: "location",
      header: "Location",
      render: (person) => person.location ?? "—",
    },
    {
      key: "email",
      header: "Email",
      render: (person) => (
        <div className="flex flex-col gap-0.5">
          {person.email && <span className="text-xs">{person.email}</span>}
          <EmailStatusBadge status={person.email_status} />
        </div>
      ),
    },
    {
      key: "dedupe",
      header: "Status",
      render: (person) => <DedupeBadge status={person.dedupe_status} />,
    },
  ];

  return (
    <DataTable
      columns={columns}
      data={people}
      getRowId={(person) => person.provider_record_id}
      onRowClick={onViewDetail}
      isLoading={isLoading}
      error={error}
      onRetry={onRetry}
      density={density}
      emptyTitle="No people match these filters"
      emptyDescription="Adjust the filters or clear them to broaden the search."
      rowActions={(person) =>
        person.dedupe_status === "existing" ? (
          <Badge variant="outline">
            <Check className="h-3 w-3" /> Saved
          </Badge>
        ) : (
          <Button
            size="sm"
            variant="outline"
            disabled={savingKey === person.provider_record_id}
            onClick={() => onSave(person)}
          >
            <Plus className="h-3.5 w-3.5" />
            {savingKey === person.provider_record_id ? "Saving…" : "Save"}
          </Button>
        )
      }
    />
  );
}
