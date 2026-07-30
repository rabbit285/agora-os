"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ApiError, apiFetch } from "@/lib/api";
import type { SearchResponse, SearchResult } from "@/lib/types";

// Entity types with a dedicated detail page; anything else falls back to
// the Knowledge Graph explorer rather than a dead link (spec section 82).
const DETAIL_ROUTES: Record<string, (id: string) => string> = {
  sales_account: (id) => `/sales/accounts/${id}`,
  support_ticket: (id) => `/support/tickets/${id}`,
  security_incident: (id) => `/security/incidents/${id}`,
  vendor: (id) => `/compliance/vendors/${id}`,
  control: (id) => `/compliance/controls/${id}`,
  audit: (id) => `/compliance/audits/${id}`,
  ai_system: (id) => `/compliance/ai-systems/${id}`,
  dpia: (id) => `/compliance/dpias/${id}`,
  ai_incident: (id) => `/compliance/ai-incidents/${id}`,
  questionnaire: (id) => `/compliance/questionnaires/${id}`,
  automation_workflow: (id) => `/automation/workflows/${id}`,
  knowledge_document: (id) => `/knowledge/${id}`,
};

function resultHref(result: SearchResult): string {
  const route = DETAIL_ROUTES[result.entity_type];
  if (route) return route(result.id);
  return `/knowledge/graph?type=${result.entity_type}&id=${result.id}`;
}

export function SearchResults({ initialQuery }: { initialQuery: string }) {
  const router = useRouter();
  const [inputValue, setInputValue] = useState(initialQuery);

  const {
    data,
    isLoading,
    error,
  } = useQuery<SearchResponse>({
    queryKey: ["search", initialQuery],
    queryFn: () =>
      apiFetch<SearchResponse>(`/api/v1/search?q=${encodeURIComponent(initialQuery)}`),
    enabled: Boolean(initialQuery.trim()),
  });

  function submit() {
    if (inputValue.trim()) {
      router.push(`/search?q=${encodeURIComponent(inputValue.trim())}`);
    }
  }

  const grouped = new Map<string, SearchResult[]>();
  for (const result of data?.results ?? []) {
    const list = grouped.get(result.module) ?? [];
    list.push(result);
    grouped.set(result.module, list);
  }

  return (
    <div>
      <PageHeader
        title="Search"
        description="Search across every module — accounts, tickets, vendors, controls, workflows, and more (spec section 47)."
      />

      <div className="mb-6 flex gap-2">
        <Input
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
          placeholder="Search…"
          className="max-w-md"
          autoFocus
        />
      </div>

      {!initialQuery.trim() ? (
        <p className="text-sm text-neutral-500">Enter a search term above.</p>
      ) : isLoading ? (
        <p className="text-sm text-neutral-500">Searching…</p>
      ) : error ? (
        <p className="text-sm text-red-600">
          {error instanceof ApiError ? error.message : "Search failed."}
        </p>
      ) : !data || data.results.length === 0 ? (
        <p className="text-sm text-neutral-500">No results for &quot;{initialQuery}&quot;.</p>
      ) : (
        <div className="flex flex-col gap-6">
          {Array.from(grouped.entries()).map(([module, results]) => (
            <div key={module}>
              <div className="mb-2 text-sm font-semibold uppercase tracking-wide text-neutral-500">
                {module}
              </div>
              <div className="flex flex-col gap-2">
                {results.map((result) => (
                  <Link key={`${result.entity_type}-${result.id}`} href={resultHref(result)}>
                    <Card className="hover:bg-neutral-50">
                      <CardContent className="flex items-center justify-between pt-6">
                        <div className="text-sm text-neutral-900">{result.label}</div>
                        <Badge variant="secondary">
                          {result.entity_type.replace(/_/g, " ")}
                        </Badge>
                      </CardContent>
                    </Card>
                  </Link>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
