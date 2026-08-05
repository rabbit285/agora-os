"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { apiFetch } from "@/lib/api";
import type { CompanyFilters, ParseQueryOut, PersonFilters } from "@/lib/types";

/** Translates a plain-English query into structured filters via
 * POST /parse-query — the AI only ever returns filter *criteria*, never
 * fabricated company/person records (see
 * tests/test_sales_lead_finder.py::test_parse_query_returns_structured_filters_not_fabricated_records).
 * The parsed filters are shown for review and only applied to the real
 * filter state (and only run as a search) when the user explicitly
 * clicks Apply — nothing here executes a search on its own. */
export function NaturalLanguageSearchBar({
  onApply,
}: {
  onApply: (companyFilters: CompanyFilters, personFilters: PersonFilters) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<ParseQueryOut | null>(null);

  const parse = useMutation({
    mutationFn: () => apiFetch<ParseQueryOut>("/api/v1/sales/lead-finder/parse-query", {
      method: "POST",
      body: { query },
    }),
    onSuccess: (data) => setResult(data),
  });

  if (!expanded) {
    return (
      <Button size="sm" variant="outline" onClick={() => setExpanded(true)} className="mb-3">
        <Sparkles className="h-3.5 w-3.5" />
        Ask in plain English
      </Button>
    );
  }

  return (
    <div className="mb-3 rounded-[var(--radius-lg)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-3">
      <Textarea
        aria-label="Describe who you're looking for in plain English"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="e.g. VP of Engineering at Series B fintech companies in Germany with 50-200 employees"
        rows={2}
      />
      <div className="mt-2 flex items-center gap-2">
        <Button size="sm" disabled={!query.trim() || parse.isPending} onClick={() => parse.mutate()}>
          {parse.isPending ? "Parsing…" : "Parse"}
        </Button>
        <Button size="sm" variant="ghost" onClick={() => setExpanded(false)}>
          Close
        </Button>
      </div>
      {parse.isError && (
        <p className="mt-2 text-xs text-[var(--critical-700)]">
          Couldn&apos;t parse that query. Try rephrasing it or use the filter sidebar directly.
        </p>
      )}
      {result && (
        <div className="mt-3 rounded-[var(--radius-md)] border border-[var(--border-default)] bg-[var(--bg-sunken)] p-3 text-xs">
          <p className="mb-2 font-medium text-[var(--fg-default)]">
            Review before applying — nothing has been searched yet.
          </p>
          <pre className="mb-2 whitespace-pre-wrap break-words text-[11px] text-[var(--fg-muted)]">
            {JSON.stringify(
              { company: result.company_filters, person: result.person_filters },
              null,
              2,
            )}
          </pre>
          {result.unsupported_criteria.length > 0 && (
            <p className="mb-2 text-[var(--warning-700)]">
              Not understood: {result.unsupported_criteria.join(", ")}
            </p>
          )}
          <Button
            size="sm"
            onClick={() => {
              onApply(result.company_filters, result.person_filters);
              setExpanded(false);
              setResult(null);
              setQuery("");
            }}
          >
            Apply to filters
          </Button>
        </div>
      )}
    </div>
  );
}
