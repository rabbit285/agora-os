"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ApiError, apiFetch } from "@/lib/api";
import type {
  PrivacyAnalysis,
  PrivacySuggestion,
  TransferMechanism,
} from "@/lib/types";

/** Privacy records Veyntra drafted, waiting for the parts only a person
 * can supply.
 *
 * The split is the whole design. Everything shown here was read out of
 * records the organization already made — an AI system's own stated
 * purpose, the users it says it affects, the vendor it names, the
 * country recorded against that vendor. What is never drafted is a
 * lawful basis, an Article 9 condition or a transfer mechanism, because
 * those are the judgements the review exists to obtain, and a
 * pre-filled one is worse than a blank because nobody checks it again.
 *
 * So each card shows the draft, names its sources so a reviewer can
 * check it rather than trust it, and asks the one or two questions that
 * turn it into a record.
 */
const SELECT_CLASS =
  "flex h-9 w-full rounded-md border border-[var(--border-strong)] bg-[var(--bg-default)] px-3 py-1 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--border-focus)]";

const LEGAL_BASES = [
  { value: "consent", label: "Consent" },
  { value: "contract", label: "Contract" },
  { value: "legal_obligation", label: "Legal obligation" },
  { value: "vital_interests", label: "Vital interests" },
  { value: "public_task", label: "Public task" },
  { value: "legitimate_interests", label: "Legitimate interests" },
];

const MECHANISMS: { value: TransferMechanism; label: string }[] = [
  { value: "adequacy_decision", label: "Adequacy decision" },
  { value: "sccs", label: "Standard Contractual Clauses" },
  { value: "bcrs", label: "Binding Corporate Rules" },
  { value: "derogation", label: "Article 49 derogation" },
];

function Sources({ suggestion }: { suggestion: PrivacySuggestion }) {
  if (suggestion.sources.length === 0) return null;
  return (
    <p className="mt-1 text-xs text-[var(--fg-subtle)]">
      Drafted from{" "}
      {suggestion.sources.map((source, index) => (
        <span key={`${source.type}-${source.id ?? index}`}>
          {index > 0 && ", "}
          <span className="text-[var(--fg-muted)]">{source.label}</span>
        </span>
      ))}
    </p>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  if (!value) return null;
  return (
    <div className="flex gap-3">
      <span className="w-32 shrink-0 text-xs text-[var(--fg-muted)]">
        {label}
      </span>
      <span className="text-sm text-[var(--fg-default)]">{value}</span>
    </div>
  );
}

function SuggestionCard({ suggestion }: { suggestion: PrivacySuggestion }) {
  const queryClient = useQueryClient();
  const [legalBasis, setLegalBasis] = useState("");
  const [retention, setRetention] = useState("");
  const [specialCategory, setSpecialCategory] = useState(false);
  const [condition, setCondition] = useState("");
  const [mechanism, setMechanism] = useState("");
  const [safeguards, setSafeguards] = useState("");
  const [error, setError] = useState<string | null>(null);

  const isActivity = suggestion.kind === "processing_activity";
  const payload = suggestion.payload;

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["compliance"] });

  const accept = useMutation({
    mutationFn: () =>
      apiFetch(
        `/api/v1/compliance/privacy/suggestions/${suggestion.id}/accept`,
        {
          method: "POST",
          body: isActivity
            ? {
                legal_basis: legalBasis,
                retention_period: retention,
                special_category: specialCategory,
                special_category_condition: condition.trim() || null,
              }
            : {
                transfer_mechanism: mechanism,
                safeguards_description: safeguards.trim() || null,
              },
        },
      ),
    onMutate: () => setError(null),
    onSuccess: invalidate,
    onError: (cause) =>
      setError(
        cause instanceof ApiError
          ? cause.message
          : "That did not go through. Nothing was created.",
      ),
  });

  const dismiss = useMutation({
    mutationFn: () =>
      apiFetch(
        `/api/v1/compliance/privacy/suggestions/${suggestion.id}/dismiss`,
        { method: "POST", body: { reason: null } },
      ),
    onSuccess: invalidate,
  });

  const ready = isActivity
    ? Boolean(legalBasis && retention.trim() && (!specialCategory || condition.trim()))
    : Boolean(mechanism);

  return (
    <Card>
      <CardContent className="pt-6">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="font-medium text-[var(--fg-default)]">
              {suggestion.title}
            </p>
            <Sources suggestion={suggestion} />
          </div>
          <span className="rounded-full bg-[var(--bg-subtle)] px-2 py-0.5 text-xs text-[var(--fg-muted)]">
            {isActivity ? "Processing activity" : "International transfer"}
          </span>
        </div>

        <div className="mt-3 flex flex-col gap-1.5">
          {isActivity ? (
            <>
              <Fact label="Purpose" value={String(payload.purpose ?? "")} />
              <Fact
                label="Data subjects"
                value={String(payload.data_subjects ?? "")}
              />
              <Fact
                label="Personal data"
                value={(
                  (payload.data_categories as string[] | undefined) ?? []
                ).join(", ")}
              />
            </>
          ) : (
            <>
              <Fact
                label="Recipient"
                value={String(payload.recipient_name ?? "")}
              />
              <Fact
                label="Destination"
                value={String(payload.destination_country ?? "")}
              />
              <Fact label="Note" value={String(payload.note ?? "")} />
            </>
          )}
        </div>

        {/* The line between what was drafted and what is being asked. */}
        <div className="mt-4 rounded-md border border-[var(--border-default)] bg-[var(--bg-subtle)] px-3 py-3">
          <p className="mb-2 text-xs font-medium text-[var(--fg-default)]">
            {isActivity
              ? "Your decision — Veyntra cannot make these"
              : "Your decision — which mechanism covers this transfer"}
          </p>

          {isActivity ? (
            <div className="flex flex-col gap-2">
              <select
                aria-label="Lawful basis"
                className={SELECT_CLASS}
                value={legalBasis}
                onChange={(event) => setLegalBasis(event.target.value)}
              >
                <option value="">Select lawful basis…</option>
                {LEGAL_BASES.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              <Input
                aria-label="Retention period"
                placeholder="Retention period (e.g. 24 months)"
                value={retention}
                onChange={(event) => setRetention(event.target.value)}
              />
              <label className="flex items-center gap-2 text-xs text-[var(--fg-muted)]">
                <input
                  type="checkbox"
                  checked={specialCategory}
                  onChange={(event) => setSpecialCategory(event.target.checked)}
                />
                This processing involves special-category data
              </label>
              {specialCategory && (
                <Input
                  aria-label="Article 9 condition"
                  placeholder="Article 9 condition (e.g. explicit consent)"
                  value={condition}
                  onChange={(event) => setCondition(event.target.value)}
                />
              )}
            </div>
          ) : (
            <div className="flex flex-col gap-2">
              <select
                aria-label="Transfer mechanism"
                className={SELECT_CLASS}
                value={mechanism}
                onChange={(event) => setMechanism(event.target.value)}
              >
                <option value="">Select transfer mechanism…</option>
                {MECHANISMS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              <Input
                aria-label="Supplementary safeguards"
                placeholder="Supplementary safeguards (optional)"
                value={safeguards}
                onChange={(event) => setSafeguards(event.target.value)}
              />
            </div>
          )}
        </div>

        <div className="mt-3 flex gap-2">
          <Button
            size="sm"
            disabled={!ready || accept.isPending}
            onClick={() => accept.mutate()}
          >
            {accept.isPending ? "Saving…" : "Confirm and create"}
          </Button>
          <Button
            size="sm"
            variant="ghost"
            disabled={dismiss.isPending}
            onClick={() => dismiss.mutate()}
          >
            Dismiss
          </Button>
        </div>

        {error && (
          <p role="alert" className="mt-2 text-sm text-[var(--fg-danger)]">
            {error}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

/** What the button says it found. Per kind, because "suggestions" is
 * what a queue is called and these are things Veyntra went and looked
 * for in records the organization already keeps. */
const DISCOVERY_LABEL: Record<string, string> = {
  transfer: "Review detected transfers",
  processing_activity: "Review detected processing",
};

export function PrivacySuggestions({ kind }: { kind: string }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);

  const { data: suggestions } = useQuery<PrivacySuggestion[]>({
    queryKey: ["compliance", "privacy", "suggestions", kind],
    queryFn: () =>
      apiFetch<PrivacySuggestion[]>(
        `/api/v1/compliance/privacy/suggestions?kind=${kind}`,
      ),
    // Drafting runs while a document is analysed, which takes minutes.
    // Whoever opened this page before that finished would otherwise sit
    // in front of "(0)" indefinitely with the suggestion already in the
    // database — the query fetched once on mount and never asked again.
    //
    // A short poll rather than a websocket: this is one small query, the
    // window it matters in is a couple of minutes after an upload, and a
    // count that is a few seconds stale is not a problem while a count
    // that is permanently wrong is.
    refetchInterval: 10_000,
    // The other way somebody arrives here: upload, switch tab, come
    // back. Window focus is disabled globally, which is right for most
    // screens and wrong for this one.
    refetchOnWindowFocus: true,
  });

  const analyse = useMutation<PrivacyAnalysis>({
    mutationFn: () =>
      apiFetch<PrivacyAnalysis>(
        "/api/v1/compliance/privacy/suggestions/analyse",
        { method: "POST" },
      ),
    onSuccess: () => {
      setOpen(true);
      queryClient.invalidateQueries({ queryKey: ["compliance", "privacy"] });
    },
  });

  const count = suggestions?.length ?? 0;

  return (
    <div className="mb-4">
      <div className="flex flex-wrap items-center gap-2">
        <Button
          size="sm"
          variant={count > 0 ? "default" : "outline"}
          onClick={() => (count > 0 ? setOpen((value) => !value) : analyse.mutate())}
          disabled={analyse.isPending}
        >
          <Sparkles className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
          {analyse.isPending
            ? "Looking…"
            : `${DISCOVERY_LABEL[kind] ?? "Review suggestions"} (${count})`}
        </Button>
        {count > 0 && (
          <Button
            size="sm"
            variant="ghost"
            disabled={analyse.isPending}
            onClick={() => analyse.mutate()}
          >
            Check again
          </Button>
        )}
      </div>

      {analyse.isSuccess && count === 0 && (
        <p className="mt-2 text-xs text-[var(--fg-subtle)]">
          No new suggestions. Veyntra identifies candidate privacy records
          from your AI systems, vendors and connected records — register those
          and check again.
        </p>
      )}

      {open && count > 0 && (
        <div className="mt-3 flex flex-col gap-3">
          <p className="text-xs text-[var(--fg-subtle)]">
            Drafted from records you already have. Nothing here is a record
            until you confirm it, and Veyntra has deliberately left the legal
            judgements blank.
          </p>
          {suggestions?.map((suggestion) => (
            <SuggestionCard key={suggestion.id} suggestion={suggestion} />
          ))}
        </div>
      )}
    </div>
  );
}
