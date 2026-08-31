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

// The route comes from the server. A lookup table here drifts the moment
// a route changes, and the failure mode is a result that looks real and
// lands on a 404 — which this table did for every sales, support,
// automation and knowledge entry after those modules were withdrawn.
function resultHref(result: SearchResult): string {
  return result.href;
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
        <p className="text-sm text-[var(--fg-muted)]">Enter a search term above.</p>
      ) : isLoading ? (
        <p className="text-sm text-[var(--fg-muted)]">Searching…</p>
      ) : error ? (
        <p className="text-sm text-[var(--critical-600)]">
          {error instanceof ApiError ? error.message : "Search failed."}
        </p>
      ) : !data || data.results.length === 0 ? (
        <p className="text-sm text-[var(--fg-muted)]">No results for &quot;{initialQuery}&quot;.</p>
      ) : (
        <div className="flex flex-col gap-6">
          {Array.from(grouped.entries()).map(([module, results]) => (
            <div key={module}>
              <div className="mb-2 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
                {module}
              </div>
              <div className="flex flex-col gap-2">
                {results.map((result) => (
                  <Link key={`${result.entity_type}-${result.id}`} href={resultHref(result)}>
                    <Card className="hover:bg-[var(--bg-surface-hover)]">
                      <CardContent className="flex items-center justify-between pt-6">
                        <div className="text-sm text-[var(--fg-default)]">{result.label}</div>
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
