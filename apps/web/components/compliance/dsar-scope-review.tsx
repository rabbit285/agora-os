"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MapPin, Plus, Wifi, WifiOff } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ApiError, apiFetch } from "@/lib/api";
import type { DsarScopeSource, DsarSearchCapability } from "@/lib/types";

/** The ranking, said in the reader's terms.
 *
 * "Probably unrelated" rather than "low" — a reviewer skimming a list
 * needs to know what the label is claiming, and "low" on its own reads
 * as a score rather than a judgement they can disagree with. */
const RELEVANCE: Record<string, { label: string; className: string }> = {
  high: { label: "High relevance", className: "text-[var(--success-700)]" },
  possible: { label: "Possible relevance", className: "text-[var(--fg-muted)]" },
  low: { label: "Probably unrelated", className: "text-[var(--fg-subtle)]" },
};

/** What Veyntra can do about a source — shown beside the relevance, and
 * never mistaken for it. A source is not more relevant for being easy to
 * search, and this label is the only place searchability appears. */
const CAPABILITY: Record<DsarSearchCapability, { label: string; searchable: boolean }> = {
  searchable: { label: "Searchable", searchable: true },
  manual_follow_up: { label: "Manual follow-up", searchable: false },
  processor_follow_up: { label: "Processor follow-up", searchable: false },
  not_connected: { label: "Not connected", searchable: false },
  unsupported: { label: "Unsupported", searchable: false },
};

const KIND_LABELS: Record<string, string> = {
  processing_activity: "Processing activity",
  ai_system: "AI system",
  vendor: "Processor",
  named_processor: "Processor — not registered",
  internal: "Veyntra record",
  manual: "Added by you",
};

/** Where to look, as a decision rather than a list.
 *
 * The panel this replaces showed the same sources as read-only text, so
 * discovery ignored them and searched a fixed set of tables instead.
 * Every row here is a choice that discovery then obeys exactly.
 *
 * Nothing is ranked out of existence. A source Veyntra thinks is
 * unrelated sits at the bottom, unticked, with its reasoning shown —
 * because the person handling the request may know something the
 * register does not, and a filter that is wrong costs a response its
 * completeness.
 */
export function DsarScopeReview({ dsarId, confirmed }: { dsarId: string; confirmed: boolean }) {
  const queryClient = useQueryClient();
  const [choices, setChoices] = useState<Record<string, boolean>>({});
  const [adding, setAdding] = useState(false);
  const [newName, setNewName] = useState("");
  const [newReason, setNewReason] = useState("");

  const { data: sources } = useQuery<DsarScopeSource[]>({
    queryKey: ["compliance", "dsars", dsarId, "scope"],
    queryFn: () => apiFetch<DsarScopeSource[]>(`/api/v1/compliance/dsars/${dsarId}/scope`),
  });

  /** This source's decision: what the person has clicked, falling back
   * to what the server already recorded.
   *
   * Derived at render rather than copied into state on load. `null` and
   * `undefined` both mean undecided, which is deliberately distinct from
   * `false` — nobody has looked at it yet, as against somebody having
   * decided to leave it out. */
  const choiceFor = (source: DsarScopeSource): boolean | null | undefined =>
    source.source_key in choices ? choices[source.source_key] : source.included;

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["compliance", "dsars", dsarId] });
  };

  const confirm = useMutation({
    mutationFn: () =>
      apiFetch(`/api/v1/compliance/dsars/${dsarId}/scope/confirm`, {
        method: "POST",
        body: {
          decisions: (sources ?? []).map((source) => ({
            source_key: source.source_key,
            included: choiceFor(source) ?? false,
          })),
        },
      }),
    onSuccess: invalidate,
  });

  const addSource = useMutation({
    mutationFn: () =>
      apiFetch(`/api/v1/compliance/dsars/${dsarId}/scope/sources`, {
        method: "POST",
        body: { name: newName, reason: newReason },
      }),
    onSuccess: () => {
      setNewName("");
      setNewReason("");
      setAdding(false);
      invalidate();
    },
  });

  if (!sources) return null;

  const undecided = sources.filter((source) => choiceFor(source) == null);
  const error = confirm.error ?? addSource.error;

  return (
    <Card className="mb-6" id="scope">
      <CardContent className="pt-6">
        <div className="mb-1 flex items-center gap-2">
          <MapPin className="h-4 w-4 text-[var(--fg-muted)]" aria-hidden="true" />
          <h2 className="font-medium text-[var(--fg-default)]">Where to look</h2>
        </div>
        <p className="mb-4 text-sm text-[var(--fg-muted)]">
          Veyntra suggests likely processing contexts and the actual data sources
          behind them, ranked by what the request tells us about this person.
          Confirm the scope before searching — discovery searches exactly what you
          confirm here, and reports honestly on everything it cannot reach.
        </p>

        {sources.length === 0 ? (
          <p className="rounded-[var(--radius-md)] border border-[var(--border-default)] bg-[var(--bg-app)] p-3 text-sm text-[var(--fg-muted)]">
            No processing activities are recorded, so Veyntra cannot suggest where to
            look. That is a gap in your register, not a finding about this person — add
            the systems you know hold personal data below.
          </p>
        ) : (
          <ul className="space-y-2">
            {sources.map((source) => {
              const checked = choiceFor(source) === true;
              const rank = RELEVANCE[source.relevance] ?? RELEVANCE.medium;
              return (
                <li
                  key={source.source_key}
                  className="rounded-[var(--radius-md)] border border-[var(--border-default)] p-3"
                >
                  <label className="flex cursor-pointer items-start gap-3">
                    <input
                      type="checkbox"
                      className="mt-1 h-4 w-4 shrink-0"
                      checked={checked}
                      disabled={confirmed}
                      aria-label={source.name}
                      onChange={(event) =>
                        setChoices((current) => ({
                          ...current,
                          [source.source_key]: event.target.checked,
                        }))
                      }
                    />
                    <span className="min-w-0 flex-1">
                      <span className="flex flex-wrap items-center gap-2">
                        <span className="text-sm font-medium text-[var(--fg-default)]">
                          {source.name}
                        </span>
                        <Badge variant="outline">{KIND_LABELS[source.kind] ?? source.kind}</Badge>
                        <span className={`text-xs ${rank.className}`}>{rank.label}</span>
                        {(() => {
                          const capability =
                            CAPABILITY[source.search_capability] ?? CAPABILITY.manual_follow_up;
                          const Icon = capability.searchable ? Wifi : WifiOff;
                          return (
                            <span className="flex items-center gap-1 text-xs text-[var(--fg-subtle)]">
                              <Icon className="h-3 w-3" aria-hidden="true" />
                              {capability.label}
                            </span>
                          );
                        })()}
                      </span>
                      <span className="mt-1 block text-xs leading-relaxed text-[var(--fg-muted)]">
                        {source.reason}
                      </span>
                      {source.relevance_reason && (
                        <span className="mt-1 block text-xs leading-relaxed text-[var(--fg-subtle)]">
                          Why this ranking: {source.relevance_reason}
                        </span>
                      )}
                      {source.potential_sources.length > 0 && (
                        <span className="mt-2 block">
                          <span className="block text-xs font-medium text-[var(--fg-muted)]">
                            Potential sources
                          </span>
                          {source.potential_sources.map((system) => (
                            <span
                              key={system.name}
                              className="mt-0.5 block text-xs text-[var(--fg-subtle)]"
                            >
                              {system.name} —{" "}
                              {(CAPABILITY[system.capability] ?? CAPABILITY.manual_follow_up)
                                .label}
                            </span>
                          ))}
                        </span>
                      )}
                    </span>
                  </label>
                </li>
              );
            })}
          </ul>
        )}

        {error && (
          <p className="mt-3 text-sm text-[var(--critical-600)]">
            {error instanceof ApiError ? error.message : "Something went wrong."}
          </p>
        )}

        {confirmed ? (
          <p className="mt-4 text-sm text-[var(--fg-muted)]">
            Scope confirmed. {sources.filter((s) => s.included).length} of {sources.length}{" "}
            source(s) are in scope.
          </p>
        ) : (
          <>
            <div className="mt-4 flex flex-wrap items-center gap-2">
              <Button
                size="sm"
                variant="outline"
                onClick={() =>
                  setChoices(
                    Object.fromEntries(
                      sources.map((source) => [
                        source.source_key,
                        // Everything the product has not argued is
                        // unrelated. Capability plays no part: a source
                        // is not worth searching because it is easy.
                        source.relevance !== "low",
                      ]),
                    ),
                  )
                }
              >
                Select all relevant
              </Button>
              <Button size="sm" variant="outline" onClick={() => setAdding((open) => !open)}>
                <Plus className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
                Add another source
              </Button>
              <Button
                size="sm"
                disabled={confirm.isPending || undecided.length > 0 || sources.length === 0}
                onClick={() => confirm.mutate()}
              >
                {confirm.isPending ? "Confirming…" : "Confirm search scope"}
              </Button>
              {undecided.length > 0 && (
                <span className="text-xs text-[var(--fg-muted)]">
                  {undecided.length} source(s) still need a decision.
                </span>
              )}
            </div>

            {adding && (
              <div className="mt-3 flex flex-col gap-2 rounded-[var(--radius-md)] border border-[var(--border-default)] p-3">
                <p className="text-xs text-[var(--fg-muted)]">
                  Your register will never be complete. Add a system you know holds this
                  person&apos;s data — Veyntra will raise a follow-up rather than
                  pretending to search it.
                </p>
                <Input
                  placeholder="Source name"
                  value={newName}
                  onChange={(event) => setNewName(event.target.value)}
                />
                <Input
                  placeholder="Why it is in scope"
                  value={newReason}
                  onChange={(event) => setNewReason(event.target.value)}
                />
                <div>
                  <Button
                    size="sm"
                    disabled={addSource.isPending || newName.length < 2 || newReason.length < 2}
                    onClick={() => addSource.mutate()}
                  >
                    Add source
                  </Button>
                </div>
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
