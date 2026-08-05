"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, RotateCcw, Upload, UserPlus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { apiFetch } from "@/lib/api";
import type {
  CompanyFilters,
  CompanySearchOut,
  CreditEstimatePreviewOut,
  EnrichmentJobOut,
  NormalizedCompanyOut,
  NormalizedPersonOut,
  SavedSearchOut,
} from "@/lib/types";

import {
  ActiveFilterChips,
  CompanyFilterFields,
  FilterSidebarShell,
} from "./filter-sidebar";
import { CompanyResultsTable } from "./results-table";
import { BulkToolbar } from "./bulk-toolbar";
import { ListPickerDialog } from "./list-picker-dialog";
import { EnrichConfirmDialog } from "./enrich-confirm-dialog";
import { CompanyDetailDialog } from "./detail-dialog";
import { SaveSearchDialog } from "./save-search-dialog";
import { NaturalLanguageSearchBar } from "./nl-search-bar";
import { ImportDialog } from "./import-dialog";
import { ManualEntryDialog } from "./manual-entry-dialog";

const PAGE_SIZE = 25;

export function CompanyWorkspace() {
  const queryClient = useQueryClient();
  const [filters, setFilters] = useState<CompanyFilters>({});
  const [appliedFilters, setAppliedFilters] = useState<CompanyFilters | null>(null);
  const [page, setPage] = useState(1);
  const [collapsed, setCollapsed] = useState(false);
  const [density, setDensity] = useState<"comfortable" | "compact">("comfortable");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [viewing, setViewing] = useState<NormalizedCompanyOut | null>(null);
  const [listPickerOpen, setListPickerOpen] = useState(false);
  const [saveSearchOpen, setSaveSearchOpen] = useState(false);
  const [enrichDialogOpen, setEnrichDialogOpen] = useState(false);
  const [enrichEstimate, setEnrichEstimate] = useState<CreditEstimatePreviewOut | null>(null);
  const [pendingEnrichAccountIds, setPendingEnrichAccountIds] = useState<string[]>([]);
  const [importOpen, setImportOpen] = useState(false);
  const [manualEntryOpen, setManualEntryOpen] = useState(false);

  const searchResult = useQuery<CompanySearchOut>({
    queryKey: ["sales", "lead-finder", "companies", appliedFilters, page],
    queryFn: () =>
      apiFetch<CompanySearchOut>("/api/v1/sales/lead-finder/companies/search", {
        method: "POST",
        body: { filters: appliedFilters, page, page_size: PAGE_SIZE },
      }),
    enabled: appliedFilters !== null,
  });

  const byId = useMemo(() => {
    const map = new Map<string, NormalizedCompanyOut>();
    for (const company of searchResult.data?.companies ?? []) map.set(company.provider_record_id, company);
    return map;
  }, [searchResult.data]);

  function runSearch(next?: CompanyFilters) {
    setPage(1);
    setSelected(new Set());
    setAppliedFilters(next ?? filters);
  }

  const saveCompany = useMutation({
    mutationFn: (company: NormalizedCompanyOut) =>
      apiFetch<{ account_id: string; created: boolean }>("/api/v1/sales/lead-finder/companies/save", {
        method: "POST",
        body: company,
      }),
    onSuccess: (_result, company) => {
      queryClient.setQueryData<CompanySearchOut | undefined>(
        ["sales", "lead-finder", "companies", appliedFilters, page],
        (current) =>
          current
            ? {
                ...current,
                companies: current.companies.map((c) =>
                  c.provider_record_id === company.provider_record_id
                    ? { ...c, dedupe_status: "existing" as const, existing_account_id: _result.account_id }
                    : c,
                ),
              }
            : current,
      );
    },
  });

  // Decision-makers found from a company's detail dialog are people, not
  // companies — a small standalone save mutation rather than plumbing
  // the whole PersonWorkspace's state through here.
  const saveDecisionMaker = useMutation({
    mutationFn: (person: NormalizedPersonOut) =>
      apiFetch<{ contact_id: string; created: boolean }>("/api/v1/sales/lead-finder/people/save", {
        method: "POST",
        body: person,
      }),
  });

  async function saveSelected(): Promise<string[]> {
    const targets = [...selected]
      .map((id) => byId.get(id))
      .filter((c): c is NormalizedCompanyOut => !!c && c.dedupe_status === "new");
    const accountIds: string[] = [];
    for (const company of targets) {
      const result = await saveCompany.mutateAsync(company);
      accountIds.push(result.account_id);
    }
    const alreadySaved = [...selected]
      .map((id) => byId.get(id))
      .filter((c): c is NormalizedCompanyOut => !!c && c.dedupe_status === "existing" && !!c.existing_account_id)
      .map((c) => c.existing_account_id as string);
    return [...accountIds, ...alreadySaved];
  }

  const addToList = useMutation({
    mutationFn: async (listId: string) => {
      const accountIds = await saveSelected();
      await Promise.all(
        accountIds.map((accountId) =>
          apiFetch(`/api/v1/sales/lead-finder/lists/${listId}/items`, {
            method: "POST",
            body: { account_id: accountId },
          }).catch(() => null),
        ),
      );
    },
    onSuccess: () => {
      setListPickerOpen(false);
      setSelected(new Set());
      queryClient.invalidateQueries({ queryKey: ["sales", "lead-finder", "companies"] });
    },
  });

  const estimateEnrich = useMutation({
    mutationFn: async () => {
      const accountIds = await saveSelected();
      setPendingEnrichAccountIds(accountIds);
      return apiFetch<CreditEstimatePreviewOut>("/api/v1/sales/lead-finder/enrich/estimate", {
        method: "POST",
        body: { operation: "enrich_company", record_ids: accountIds },
      });
    },
    onSuccess: (estimate) => setEnrichEstimate(estimate),
  });

  const runEnrich = useMutation({
    mutationFn: () =>
      apiFetch<EnrichmentJobOut>("/api/v1/sales/lead-finder/enrich/bulk", {
        method: "POST",
        body: { operation: "enrich_company", record_ids: pendingEnrichAccountIds },
      }),
    onSuccess: () => {
      setEnrichDialogOpen(false);
      setSelected(new Set());
      queryClient.invalidateQueries({ queryKey: ["sales", "lead-finder", "companies"] });
    },
  });

  const saveSearch = useMutation({
    mutationFn: (name: string) =>
      apiFetch<SavedSearchOut>("/api/v1/sales/lead-finder/saved-searches", {
        method: "POST",
        body: { name, search_type: "company", filters: appliedFilters ?? filters, density },
      }),
    onSuccess: () => {
      setSaveSearchOpen(false);
      queryClient.invalidateQueries({ queryKey: ["sales", "lead-finder", "lists", "saved-searches"] });
    },
  });

  const total = searchResult.data?.total_available ?? null;
  const hasNextPage = total !== null ? page * PAGE_SIZE < total : (searchResult.data?.companies.length ?? 0) === PAGE_SIZE;

  return (
    <div className="flex gap-4">
      <FilterSidebarShell
        collapsed={collapsed}
        onToggleCollapsed={() => setCollapsed((v) => !v)}
        onApply={() => runSearch()}
        onClear={() => {
          setFilters({});
          setAppliedFilters(null);
        }}
      >
        <CompanyFilterFields filters={filters} onChange={setFilters} />
      </FilterSidebarShell>

      <div className="min-w-0 flex-1">
        <NaturalLanguageSearchBar
          onApply={(companyFilters) => {
            setFilters(companyFilters);
            runSearch(companyFilters);
          }}
        />

        {appliedFilters && (
          <ActiveFilterChips
            filters={appliedFilters}
            onRemove={(key) => {
              const next = { ...appliedFilters, [key]: undefined };
              setFilters(next);
              runSearch(next);
            }}
          />
        )}

        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2 text-xs text-[var(--fg-muted)]">
            {searchResult.data && (
              <span>
                {searchResult.data.companies.length} result{searchResult.data.companies.length === 1 ? "" : "s"}
                {total !== null ? ` of ${total}` : ""} via {searchResult.data.provider}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <Button size="sm" variant="outline" onClick={() => setImportOpen(true)}>
              <Upload className="h-3.5 w-3.5" />
              Import CSV
            </Button>
            <Button size="sm" variant="outline" onClick={() => setManualEntryOpen(true)}>
              <UserPlus className="h-3.5 w-3.5" />
              Add manually
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={!appliedFilters}
              onClick={() => setSaveSearchOpen(true)}
            >
              Save search
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setDensity((d) => (d === "comfortable" ? "compact" : "comfortable"))}
            >
              {density === "comfortable" ? "Compact" : "Comfortable"}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              disabled={!appliedFilters}
              onClick={() => searchResult.refetch()}
              aria-label="Refresh results"
            >
              <RotateCcw className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>

        <BulkToolbar
          count={selected.size}
          onClear={() => setSelected(new Set())}
          onSave={() => saveSelected()}
          savePending={saveCompany.isPending}
          onAddToList={() => setListPickerOpen(true)}
          onEnrich={() => {
            setEnrichDialogOpen(true);
            estimateEnrich.mutate();
          }}
        />

        {!appliedFilters ? (
          <div className="rounded-[var(--radius-lg)] border border-dashed border-[var(--border-default)] px-6 py-16 text-center text-sm text-[var(--fg-muted)]">
            Set filters or ask in plain English, then click Search to find companies.
          </div>
        ) : (
          <>
            <CompanyResultsTable
              companies={searchResult.data?.companies}
              isLoading={searchResult.isLoading}
              error={searchResult.error}
              onRetry={() => searchResult.refetch()}
              density={density}
              selected={selected}
              onToggleSelect={(id) =>
                setSelected((current) => {
                  const next = new Set(current);
                  if (next.has(id)) next.delete(id);
                  else next.add(id);
                  return next;
                })
              }
              onSave={(company) => saveCompany.mutate(company)}
              savingKey={saveCompany.isPending ? saveCompany.variables?.provider_record_id ?? null : null}
              onViewDetail={setViewing}
            />
            {searchResult.data && searchResult.data.companies.length > 0 && (
              <div className="mt-3 flex items-center justify-between">
                <Button size="sm" variant="outline" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
                  <ChevronLeft className="h-3.5 w-3.5" /> Previous
                </Button>
                <span className="text-xs text-[var(--fg-muted)]">Page {page}</span>
                <Button size="sm" variant="outline" disabled={!hasNextPage} onClick={() => setPage((p) => p + 1)}>
                  Next <ChevronRight className="h-3.5 w-3.5" />
                </Button>
              </div>
            )}
          </>
        )}
      </div>

      <ListPickerDialog
        open={listPickerOpen}
        onOpenChange={setListPickerOpen}
        listType="company"
        onConfirm={(listId) => addToList.mutate(listId)}
        isSubmitting={addToList.isPending}
      />
      <EnrichConfirmDialog
        open={enrichDialogOpen}
        onOpenChange={setEnrichDialogOpen}
        estimate={enrichEstimate}
        isEstimating={estimateEnrich.isPending}
        onConfirm={() => runEnrich.mutate()}
        isEnriching={runEnrich.isPending}
      />
      <CompanyDetailDialog
        company={viewing}
        onOpenChange={(open) => !open && setViewing(null)}
        onSave={(company) => saveCompany.mutate(company)}
        saving={saveCompany.isPending}
        onSavePerson={(person) => saveDecisionMaker.mutate(person)}
        savingPerson={saveDecisionMaker.isPending}
      />
      <SaveSearchDialog
        open={saveSearchOpen}
        onOpenChange={setSaveSearchOpen}
        onConfirm={(name) => saveSearch.mutate(name)}
        isSubmitting={saveSearch.isPending}
      />
      <ImportDialog
        open={importOpen}
        onOpenChange={setImportOpen}
        recordType="company"
        onImported={() => queryClient.invalidateQueries({ queryKey: ["sales", "accounts"] })}
      />
      <ManualEntryDialog
        open={manualEntryOpen}
        onOpenChange={setManualEntryOpen}
        recordType="company"
        onCreated={() => {}}
      />
    </div>
  );
}
