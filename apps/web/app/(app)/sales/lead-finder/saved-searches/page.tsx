"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Play, Trash2 } from "lucide-react";

import { DataTable, type DataTableColumn } from "@/components/data-table";
import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { apiFetch } from "@/lib/api";
import type {
  CompanySearchOut,
  NormalizedCompanyOut,
  NormalizedPersonOut,
  PersonSearchOut,
  SavedSearchOut,
} from "@/lib/types";

function RunResultsDialog({
  searchType,
  results,
  onOpenChange,
}: {
  searchType: "company" | "person" | null;
  results: CompanySearchOut | PersonSearchOut | null;
  onOpenChange: (open: boolean) => void;
}) {
  const queryClient = useQueryClient();

  const saveCompany = useMutation({
    mutationFn: (company: NormalizedCompanyOut) =>
      apiFetch("/api/v1/sales/lead-finder/companies/save", { method: "POST", body: company }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["sales", "lead-finder", "companies"] }),
  });
  const savePerson = useMutation({
    mutationFn: (person: NormalizedPersonOut) =>
      apiFetch("/api/v1/sales/lead-finder/people/save", { method: "POST", body: person }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["sales", "lead-finder", "people"] }),
  });

  return (
    <Dialog open={results !== null} onOpenChange={onOpenChange}>
      {results && (
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Search results</DialogTitle>
          </DialogHeader>
          <div className="max-h-96 overflow-y-auto">
            {searchType === "company" ? (
              <ul className="flex flex-col gap-2">
                {(results as CompanySearchOut).companies.map((company) => (
                  <li
                    key={company.provider_record_id}
                    className="flex items-center justify-between rounded-[var(--radius-md)] border border-[var(--border-default)] px-3 py-2"
                  >
                    <div>
                      <p className="text-sm font-medium">{company.name}</p>
                      <p className="text-xs text-[var(--fg-muted)]">{company.domain}</p>
                    </div>
                    {company.dedupe_status === "existing" ? (
                      <Badge variant="outline">Saved</Badge>
                    ) : (
                      <Button size="sm" variant="outline" onClick={() => saveCompany.mutate(company)}>
                        Save
                      </Button>
                    )}
                  </li>
                ))}
              </ul>
            ) : (
              <ul className="flex flex-col gap-2">
                {(results as PersonSearchOut).people.map((person) => (
                  <li
                    key={person.provider_record_id}
                    className="flex items-center justify-between rounded-[var(--radius-md)] border border-[var(--border-default)] px-3 py-2"
                  >
                    <div>
                      <p className="text-sm font-medium">{person.full_name}</p>
                      <p className="text-xs text-[var(--fg-muted)]">{person.title ?? person.email}</p>
                    </div>
                    {person.dedupe_status === "existing" ? (
                      <Badge variant="outline">Saved</Badge>
                    ) : (
                      <Button size="sm" variant="outline" onClick={() => savePerson.mutate(person)}>
                        Save
                      </Button>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </DialogContent>
      )}
    </Dialog>
  );
}

export default function SavedSearchesPage() {
  const queryClient = useQueryClient();
  const [runResults, setRunResults] = useState<{
    type: "company" | "person";
    data: CompanySearchOut | PersonSearchOut;
  } | null>(null);

  const { data: searches, isLoading, error, refetch } = useQuery<SavedSearchOut[]>({
    queryKey: ["sales", "lead-finder", "saved-searches"],
    queryFn: () => apiFetch<SavedSearchOut[]>("/api/v1/sales/lead-finder/saved-searches"),
  });

  const runSearch = useMutation({
    mutationFn: (search: SavedSearchOut) =>
      apiFetch<CompanySearchOut | PersonSearchOut>(
        `/api/v1/sales/lead-finder/saved-searches/${search.id}/run`,
        { method: "POST" },
      ),
    onSuccess: (data, search) => {
      setRunResults({ type: search.search_type, data });
      queryClient.invalidateQueries({ queryKey: ["sales", "lead-finder", "saved-searches"] });
    },
  });

  const deleteSearch = useMutation({
    mutationFn: (id: string) =>
      apiFetch(`/api/v1/sales/lead-finder/saved-searches/${id}`, { method: "DELETE" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["sales", "lead-finder", "saved-searches"] }),
  });

  const columns: DataTableColumn<SavedSearchOut>[] = [
    {
      key: "name",
      header: "Name",
      render: (search) => <span className="font-medium">{search.name}</span>,
      sortValue: (search) => search.name.toLowerCase(),
    },
    {
      key: "type",
      header: "Type",
      render: (search) => <Badge variant="outline">{search.search_type}</Badge>,
    },
    {
      key: "provider",
      header: "Provider",
      render: (search) => search.provider,
    },
    {
      key: "last_run",
      header: "Last run",
      render: (search) =>
        search.last_executed_at ? new Date(search.last_executed_at).toLocaleString() : "Never",
      sortValue: (search) => search.last_executed_at ?? "",
    },
    {
      key: "last_count",
      header: "Last results",
      render: (search) => search.last_result_count ?? "—",
    },
    {
      key: "shared",
      header: "Shared",
      render: (search) => (search.is_shared ? <Badge variant="secondary">Shared</Badge> : "—"),
    },
  ];

  return (
    <div>
      <PageHeader
        title="Saved Searches"
        description="Re-run a saved Lead Finder search or clean up ones you no longer need."
      />
      <DataTable
        columns={columns}
        data={searches}
        getRowId={(search) => search.id}
        isLoading={isLoading}
        error={error}
        onRetry={() => refetch()}
        emptyTitle="No saved searches yet"
        emptyDescription="Save a search from the Lead Finder's Companies or People tab."
        rowActions={(search) => (
          <div className="flex justify-end gap-1">
            <Button
              size="sm"
              variant="ghost"
              disabled={runSearch.isPending}
              onClick={() => runSearch.mutate(search)}
              aria-label={`Run ${search.name}`}
            >
              <Play className="h-3.5 w-3.5" />
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => deleteSearch.mutate(search.id)}
              aria-label={`Delete ${search.name}`}
            >
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          </div>
        )}
      />
      <RunResultsDialog
        searchType={runResults?.type ?? null}
        results={runResults?.data ?? null}
        onOpenChange={(open) => !open && setRunResults(null)}
      />
    </div>
  );
}
