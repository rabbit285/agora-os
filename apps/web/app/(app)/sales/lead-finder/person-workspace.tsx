"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, RotateCcw, Upload, UserPlus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { apiFetch } from "@/lib/api";
import type {
  CreditEstimatePreviewOut,
  EnrichmentJobOut,
  NormalizedPersonOut,
  PersonFilters,
  PersonSearchOut,
  SavedSearchOut,
} from "@/lib/types";

import { ActiveFilterChips, FilterSidebarShell, PersonFilterFields } from "./filter-sidebar";
import { PersonResultsTable } from "./results-table";
import { describeProviderSearchError } from "./provider-error";
import { BulkToolbar } from "./bulk-toolbar";
import { ListPickerDialog } from "./list-picker-dialog";
import { EnrichConfirmDialog } from "./enrich-confirm-dialog";
import { PersonDetailDialog } from "./detail-dialog";
import { SaveSearchDialog } from "./save-search-dialog";
import { NaturalLanguageSearchBar } from "./nl-search-bar";
import { ImportDialog } from "./import-dialog";
import { ManualEntryDialog } from "./manual-entry-dialog";

const PAGE_SIZE = 25;

export function PersonWorkspace() {
  const queryClient = useQueryClient();
  const [filters, setFilters] = useState<PersonFilters>({});
  const [appliedFilters, setAppliedFilters] = useState<PersonFilters | null>(null);
  const [page, setPage] = useState(1);
  const [collapsed, setCollapsed] = useState(false);
  const [density, setDensity] = useState<"comfortable" | "compact">("comfortable");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [viewing, setViewing] = useState<NormalizedPersonOut | null>(null);
  const [listPickerOpen, setListPickerOpen] = useState(false);
  const [saveSearchOpen, setSaveSearchOpen] = useState(false);
  const [enrichDialogOpen, setEnrichDialogOpen] = useState(false);
  const [enrichEstimate, setEnrichEstimate] = useState<CreditEstimatePreviewOut | null>(null);
  const [pendingEnrichContactIds, setPendingEnrichContactIds] = useState<string[]>([]);
  const [importOpen, setImportOpen] = useState(false);
  const [manualEntryOpen, setManualEntryOpen] = useState(false);

  const searchResult = useQuery<PersonSearchOut>({
    queryKey: ["sales", "lead-finder", "people", appliedFilters, page],
    queryFn: () =>
      apiFetch<PersonSearchOut>("/api/v1/sales/lead-finder/people/search", {
        method: "POST",
        body: { filters: appliedFilters, page, page_size: PAGE_SIZE },
      }),
    enabled: appliedFilters !== null,
  });

  const byId = useMemo(() => {
    const map = new Map<string, NormalizedPersonOut>();
    for (const person of searchResult.data?.people ?? []) map.set(person.provider_record_id, person);
    return map;
  }, [searchResult.data]);

  function runSearch(next?: PersonFilters) {
    setPage(1);
    setSelected(new Set());
    setAppliedFilters(next ?? filters);
  }

  const savePerson = useMutation({
    mutationFn: (person: NormalizedPersonOut) =>
      apiFetch<{ contact_id: string; created: boolean }>("/api/v1/sales/lead-finder/people/save", {
        method: "POST",
        body: person,
      }),
    onSuccess: (result, person) => {
      queryClient.setQueryData<PersonSearchOut | undefined>(
        ["sales", "lead-finder", "people", appliedFilters, page],
        (current) =>
          current
            ? {
                ...current,
                people: current.people.map((p) =>
                  p.provider_record_id === person.provider_record_id
                    ? { ...p, dedupe_status: "existing" as const, existing_contact_id: result.contact_id }
                    : p,
                ),
              }
            : current,
      );
    },
  });

  async function saveSelected(): Promise<string[]> {
    const targets = [...selected]
      .map((id) => byId.get(id))
      .filter((p): p is NormalizedPersonOut => !!p && p.dedupe_status === "new");
    const contactIds: string[] = [];
    for (const person of targets) {
      const result = await savePerson.mutateAsync(person);
      contactIds.push(result.contact_id);
    }
    const alreadySaved = [...selected]
      .map((id) => byId.get(id))
      .filter((p): p is NormalizedPersonOut => !!p && p.dedupe_status === "existing" && !!p.existing_contact_id)
      .map((p) => p.existing_contact_id as string);
    return [...contactIds, ...alreadySaved];
  }

  const addToList = useMutation({
    mutationFn: async (listId: string) => {
      const contactIds = await saveSelected();
      await Promise.all(
        contactIds.map((contactId) =>
          apiFetch(`/api/v1/sales/lead-finder/lists/${listId}/items`, {
            method: "POST",
            body: { contact_id: contactId },
          }).catch(() => null),
        ),
      );
    },
    onSuccess: () => {
      setListPickerOpen(false);
      setSelected(new Set());
      queryClient.invalidateQueries({ queryKey: ["sales", "lead-finder", "people"] });
    },
  });

  const estimateEnrich = useMutation({
    mutationFn: async () => {
      const contactIds = await saveSelected();
      setPendingEnrichContactIds(contactIds);
      return apiFetch<CreditEstimatePreviewOut>("/api/v1/sales/lead-finder/enrich/estimate", {
        method: "POST",
        body: { operation: "enrich_person", record_ids: contactIds },
      });
    },
    onSuccess: (estimate) => setEnrichEstimate(estimate),
  });

  const runEnrich = useMutation({
    mutationFn: () =>
      apiFetch<EnrichmentJobOut>("/api/v1/sales/lead-finder/enrich/bulk", {
        method: "POST",
        body: { operation: "enrich_person", record_ids: pendingEnrichContactIds },
      }),
    onSuccess: () => {
      setEnrichDialogOpen(false);
      setSelected(new Set());
      queryClient.invalidateQueries({ queryKey: ["sales", "lead-finder", "people"] });
    },
  });

  const saveSearch = useMutation({
    mutationFn: (name: string) =>
      apiFetch<SavedSearchOut>("/api/v1/sales/lead-finder/saved-searches", {
        method: "POST",
        body: { name, search_type: "person", filters: appliedFilters ?? filters, density },
      }),
    onSuccess: () => {
      setSaveSearchOpen(false);
      queryClient.invalidateQueries({ queryKey: ["sales", "lead-finder", "lists", "saved-searches"] });
    },
  });

  const total = searchResult.data?.total_available ?? null;
  const hasNextPage = total !== null ? page * PAGE_SIZE < total : (searchResult.data?.people.length ?? 0) === PAGE_SIZE;

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
        <PersonFilterFields filters={filters} onChange={setFilters} />
      </FilterSidebarShell>

      <div className="min-w-0 flex-1">
        <NaturalLanguageSearchBar
          onApply={(_companyFilters, personFilters) => {
            setFilters(personFilters);
            runSearch(personFilters);
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
                {searchResult.data.people.length} result{searchResult.data.people.length === 1 ? "" : "s"}
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
          savePending={savePerson.isPending}
          onAddToList={() => setListPickerOpen(true)}
          onEnrich={() => {
            setEnrichDialogOpen(true);
            estimateEnrich.mutate();
          }}
        />

        {!appliedFilters ? (
          <div className="rounded-[var(--radius-lg)] border border-dashed border-[var(--border-default)] px-6 py-16 text-center text-sm text-[var(--fg-muted)]">
            Set filters or ask in plain English, then click Search to find people.
          </div>
        ) : (
          <>
            <PersonResultsTable
              people={searchResult.data?.people}
              isLoading={searchResult.isLoading}
              error={describeProviderSearchError(searchResult.error, "People Search") ?? searchResult.error}
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
              onSave={(person) => savePerson.mutate(person)}
              savingKey={savePerson.isPending ? savePerson.variables?.provider_record_id ?? null : null}
              onViewDetail={setViewing}
            />
            {searchResult.data && searchResult.data.people.length > 0 && (
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
        listType="person"
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
      <PersonDetailDialog
        person={viewing}
        onOpenChange={(open) => !open && setViewing(null)}
        onSave={(person) => savePerson.mutate(person)}
        saving={savePerson.isPending}
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
        recordType="person"
        onImported={() => queryClient.invalidateQueries({ queryKey: ["sales", "contacts"] })}
      />
      <ManualEntryDialog
        open={manualEntryOpen}
        onOpenChange={setManualEntryOpen}
        recordType="person"
        onCreated={() => {}}
      />
    </div>
  );
}
