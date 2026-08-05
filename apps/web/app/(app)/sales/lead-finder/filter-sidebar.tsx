"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";
import type { CompanyFilters, PersonFilters } from "@/lib/types";

function parseList(value: string): string[] {
  return value
    .split(",")
    .map((v) => v.trim())
    .filter(Boolean);
}

function FilterGroup({
  title,
  defaultOpen = true,
  children,
}: {
  title: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border-b border-[var(--border-default)] py-3 last:border-b-0">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="mb-2 flex w-full items-center justify-between text-xs font-semibold uppercase tracking-wide text-[var(--fg-muted)]"
      >
        {title}
        {open ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
      </button>
      {open && <div className="flex flex-col gap-3">{children}</div>}
    </div>
  );
}

function ListField({
  id,
  label,
  value,
  onChange,
  placeholder,
}: {
  id: string;
  label: string;
  value: string[] | undefined;
  onChange: (next: string[]) => void;
  placeholder?: string;
}) {
  return (
    <div>
      <Label htmlFor={id} className="mb-1 block text-xs">
        {label}
      </Label>
      <Input
        id={id}
        defaultValue={(value ?? []).join(", ")}
        onBlur={(e) => onChange(parseList(e.target.value))}
        placeholder={placeholder ?? "Comma-separated"}
        className="text-xs"
      />
    </div>
  );
}

/** Collapsible left-hand filter sidebar shared by the Companies and People
 * workspaces (spec: "collapsible filter sidebar" — no vertical filter
 * sidebar existed anywhere in the app before this feature, see the
 * design-system survey). Array fields are comma-separated text rather
 * than a fabricated autocomplete/typeahead — this is real, editable input
 * with no invented suggestion data behind it. */
export function FilterSidebarShell({
  collapsed,
  onToggleCollapsed,
  onApply,
  onClear,
  children,
}: {
  collapsed: boolean;
  onToggleCollapsed: () => void;
  onApply: () => void;
  onClear: () => void;
  children: React.ReactNode;
}) {
  if (collapsed) {
    return (
      <div className="flex w-10 shrink-0 flex-col items-center border-r border-[var(--border-default)] pt-2">
        <Button variant="ghost" size="icon" onClick={onToggleCollapsed} aria-label="Expand filters">
          <ChevronRight className="h-4 w-4" />
        </Button>
      </div>
    );
  }
  return (
    <aside className="flex w-64 shrink-0 flex-col border-r border-[var(--border-default)] pr-3">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-sm font-semibold text-[var(--fg-default)]">Filters</span>
        <Button variant="ghost" size="icon" onClick={onToggleCollapsed} aria-label="Collapse filters">
          <X className="h-4 w-4" />
        </Button>
      </div>
      <div className="flex-1 overflow-y-auto">{children}</div>
      <div className="mt-3 flex gap-2 border-t border-[var(--border-default)] pt-3">
        <Button size="sm" className="flex-1" onClick={onApply}>
          Search
        </Button>
        <Button size="sm" variant="outline" onClick={onClear}>
          Clear
        </Button>
      </div>
    </aside>
  );
}

export function CompanyFilterFields({
  filters,
  onChange,
}: {
  filters: CompanyFilters;
  onChange: (next: CompanyFilters) => void;
}) {
  return (
    <>
      <FilterGroup title="Company">
        <div>
          <Label htmlFor="company-filter-name" className="mb-1 block text-xs">
            Name
          </Label>
          <Input
            id="company-filter-name"
            value={filters.name ?? ""}
            onChange={(e) => onChange({ ...filters, name: e.target.value || undefined })}
            className="text-xs"
          />
        </div>
        <div>
          <Label htmlFor="company-filter-domain" className="mb-1 block text-xs">
            Domain
          </Label>
          <Input
            id="company-filter-domain"
            value={filters.domain ?? ""}
            onChange={(e) => onChange({ ...filters, domain: e.target.value || undefined })}
            placeholder="acme.com"
            className="text-xs"
          />
        </div>
        <ListField
          id="company-filter-locations"
          label="Locations"
          value={filters.locations}
          onChange={(next) => onChange({ ...filters, locations: next })}
        />
        <ListField
          id="company-filter-industries"
          label="Industries"
          value={filters.industries}
          onChange={(next) => onChange({ ...filters, industries: next })}
        />
        <div className="grid grid-cols-2 gap-2">
          <div>
            <Label htmlFor="company-filter-min-employees" className="mb-1 block text-xs">
              Min employees
            </Label>
            <Input
              id="company-filter-min-employees"
              type="number"
              min={0}
              value={filters.min_employee_count ?? ""}
              onChange={(e) =>
                onChange({
                  ...filters,
                  min_employee_count: e.target.value ? Number(e.target.value) : undefined,
                })
              }
              className="text-xs"
            />
          </div>
          <div>
            <Label htmlFor="company-filter-max-employees" className="mb-1 block text-xs">
              Max employees
            </Label>
            <Input
              id="company-filter-max-employees"
              type="number"
              min={0}
              value={filters.max_employee_count ?? ""}
              onChange={(e) =>
                onChange({
                  ...filters,
                  max_employee_count: e.target.value ? Number(e.target.value) : undefined,
                })
              }
              className="text-xs"
            />
          </div>
        </div>
      </FilterGroup>
      <FilterGroup title="Signals" defaultOpen={false}>
        <ListField
          id="company-filter-technologies"
          label="Technologies"
          value={filters.technologies}
          onChange={(next) => onChange({ ...filters, technologies: next })}
        />
        <ListField
          id="company-filter-keywords"
          label="Keywords"
          value={filters.keywords}
          onChange={(next) => onChange({ ...filters, keywords: next })}
        />
        <ListField
          id="company-filter-funding-stages"
          label="Funding stages"
          value={filters.funding_stages}
          onChange={(next) => onChange({ ...filters, funding_stages: next })}
          placeholder="seed, series_a"
        />
        <div className="grid grid-cols-2 gap-2">
          <div>
            <Label htmlFor="company-filter-min-revenue" className="mb-1 block text-xs">
              Min revenue
            </Label>
            <Input
              id="company-filter-min-revenue"
              type="number"
              min={0}
              value={filters.min_revenue ?? ""}
              onChange={(e) =>
                onChange({ ...filters, min_revenue: e.target.value ? Number(e.target.value) : undefined })
              }
              className="text-xs"
            />
          </div>
          <div>
            <Label htmlFor="company-filter-max-revenue" className="mb-1 block text-xs">
              Max revenue
            </Label>
            <Input
              id="company-filter-max-revenue"
              type="number"
              min={0}
              value={filters.max_revenue ?? ""}
              onChange={(e) =>
                onChange({ ...filters, max_revenue: e.target.value ? Number(e.target.value) : undefined })
              }
              className="text-xs"
            />
          </div>
        </div>
      </FilterGroup>
    </>
  );
}

export function PersonFilterFields({
  filters,
  onChange,
}: {
  filters: PersonFilters;
  onChange: (next: PersonFilters) => void;
}) {
  return (
    <FilterGroup title="People">
      <div>
        <Label htmlFor="person-filter-name" className="mb-1 block text-xs">
          Name
        </Label>
        <Input
          id="person-filter-name"
          value={filters.name ?? ""}
          onChange={(e) => onChange({ ...filters, name: e.target.value || undefined })}
          className="text-xs"
        />
      </div>
      <div>
        <Label htmlFor="person-filter-company-domain" className="mb-1 block text-xs">
          Company domain
        </Label>
        <Input
          id="person-filter-company-domain"
          value={filters.current_company_domain ?? ""}
          onChange={(e) =>
            onChange({ ...filters, current_company_domain: e.target.value || undefined })
          }
          placeholder="acme.com"
          className="text-xs"
        />
      </div>
      <ListField
        id="person-filter-titles"
        label="Titles"
        value={filters.titles}
        onChange={(next) => onChange({ ...filters, titles: next })}
      />
      <ListField
        id="person-filter-title-keywords"
        label="Title keywords"
        value={filters.title_keywords}
        onChange={(next) => onChange({ ...filters, title_keywords: next })}
      />
      <ListField
        id="person-filter-seniorities"
        label="Seniorities"
        value={filters.seniorities}
        onChange={(next) => onChange({ ...filters, seniorities: next })}
        placeholder="director, vp, c_suite"
      />
      <ListField
        id="person-filter-departments"
        label="Departments"
        value={filters.departments}
        onChange={(next) => onChange({ ...filters, departments: next })}
      />
      <ListField
        id="person-filter-locations"
        label="Locations"
        value={filters.locations}
        onChange={(next) => onChange({ ...filters, locations: next })}
      />
      <label className="flex items-center gap-2 text-xs text-[var(--fg-default)]">
        <input
          type="checkbox"
          checked={filters.require_verified_email ?? false}
          onChange={(e) => onChange({ ...filters, require_verified_email: e.target.checked })}
          className="h-3.5 w-3.5 accent-[var(--brand-primary)]"
        />
        Require verified email
      </label>
    </FilterGroup>
  );
}

const FILTER_LABELS: Record<string, string> = {
  name: "Name",
  domain: "Domain",
  locations: "Locations",
  min_employee_count: "Min employees",
  max_employee_count: "Max employees",
  industries: "Industries",
  keywords: "Keywords",
  min_revenue: "Min revenue",
  max_revenue: "Max revenue",
  funding_stages: "Funding stages",
  technologies: "Technologies",
  current_company_domain: "Company domain",
  titles: "Titles",
  title_keywords: "Title keywords",
  seniorities: "Seniorities",
  departments: "Departments",
  require_verified_email: "Verified email only",
};

/** Active-filter chips row — every applied filter shown with a one-click
 * remove, so the user always sees exactly what's constraining the results
 * (spec: "active-filter chips"). */
export function ActiveFilterChips<T extends Record<string, unknown>>({
  filters,
  onRemove,
}: {
  filters: T;
  onRemove: (key: keyof T) => void;
}) {
  const entries = Object.entries(filters).filter(([, value]) => {
    if (value === undefined || value === null || value === "") return false;
    if (Array.isArray(value)) return value.length > 0;
    if (typeof value === "boolean") return value === true;
    return true;
  });
  if (entries.length === 0) return null;
  return (
    <div className="mb-3 flex flex-wrap gap-1.5">
      {entries.map(([key, value]) => (
        <span
          key={key}
          className={cn(
            "inline-flex items-center gap-1 rounded-full border border-[var(--border-default)]",
            "bg-[var(--bg-sunken)] px-2 py-0.5 text-[11px] text-[var(--fg-default)]",
          )}
        >
          {FILTER_LABELS[key] ?? key}
          {Array.isArray(value) ? `: ${value.join(", ")}` : typeof value === "boolean" ? "" : `: ${String(value)}`}
          <button
            type="button"
            onClick={() => onRemove(key as keyof T)}
            aria-label={`Remove ${FILTER_LABELS[key] ?? key} filter`}
            className="text-[var(--fg-subtle)] hover:text-[var(--fg-default)]"
          >
            <X className="h-3 w-3" />
          </button>
        </span>
      ))}
    </div>
  );
}
