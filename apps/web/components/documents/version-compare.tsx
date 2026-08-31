"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, GitCompare, Minus, PencilLine, Plus } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { apiFetch } from "@/lib/api";
import type { DocumentVersion, VersionDiff } from "@/lib/types";

/** What changed between two versions of a document.
 *
 * "Version 2 is current" is not what a reviewer wants to know. They want
 * the section that moved, because that is what decides whether the
 * control resting on it still holds and whether the approval on it can
 * stand.
 *
 * Sections, not lines. A policy re-flowed by a word processor changes
 * every line and says nothing new, and a diff that cries wolf on
 * formatting is a diff nobody reads. Unchanged sections are collapsed by
 * default for the same reason.
 */
export function VersionCompare({
  documentId,
  versions,
  currentFileId,
}: {
  documentId: string;
  versions: DocumentVersion[];
  currentFileId: string;
}) {
  const previousVersion = pickPrevious(versions, currentFileId);
  // Derived, not frozen at mount. Accepting a version is what *creates*
  // the second version, so a default captured in `useState` is captured
  // when there is nothing to compare against — and stays null forever,
  // leaving this panel permanently blank for the one person who just
  // made the version. State holds only a choice the reader actually made.
  const [chosen, setChosen] = useState<string | null>(null);
  const against = chosen ?? previousVersion?.file_id ?? null;
  const [showUnchanged, setShowUnchanged] = useState(false);

  const { data: diff, isPending } = useQuery<VersionDiff>({
    queryKey: ["compliance", "documents", documentId, "compare", against],
    queryFn: () =>
      apiFetch<VersionDiff>(
        `/api/v1/compliance/documents/${documentId}/compare?against=${against}`,
      ),
    enabled: Boolean(against),
  });

  if (versions.length < 2) return null;

  const comparable = versions.filter(
    (version) => version.file_id !== currentFileId,
  );
  const shown = diff?.changes.filter(
    (change) => showUnchanged || change.change !== "unchanged",
  );

  return (
    <section aria-labelledby="version-compare" className="mt-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2
          id="version-compare"
          className="flex items-center gap-2 text-sm font-semibold text-[var(--fg-default)]"
        >
          <GitCompare
            className="h-4 w-4 text-[var(--fg-muted)]"
            aria-hidden="true"
          />
          What changed
        </h2>

        <label className="flex items-center gap-2 text-sm text-[var(--fg-muted)]">
          Compare with
          <select
            value={against ?? ""}
            onChange={(event) => setChosen(event.target.value || null)}
            className="rounded-[var(--radius-md)] border border-[var(--border-default)] bg-[var(--bg-surface)] px-2 py-1 text-sm text-[var(--fg-default)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--border-focus)]"
          >
            {comparable.map((version) => (
              <option key={version.file_id} value={version.file_id}>
                {version.version_label ?? version.filename}
              </option>
            ))}
          </select>
        </label>
      </div>

      {isPending && against && (
        <p className="mt-3 text-sm text-[var(--fg-subtle)]">Comparing…</p>
      )}

      {diff && (
        <>
          <p className="mt-3 flex flex-wrap items-center gap-2 text-sm text-[var(--fg-default)]">
            <span className="text-[var(--fg-muted)]">
              {diff.previous_label ?? "Earlier version"}
            </span>
            <ArrowRight
              className="h-4 w-4 text-[var(--fg-subtle)]"
              aria-hidden="true"
            />
            <span className="text-[var(--fg-muted)]">
              {diff.current_label ?? "This version"}
            </span>
            <span className="font-medium">{diff.headline}</span>
          </p>

          {shown && shown.length > 0 ? (
            <ul className="mt-3 flex flex-col gap-2">
              {shown.map((change) => (
                <li key={`${change.change}-${change.section ?? "opening"}`}>
                  <ChangeRow change={change} />
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-3 text-sm text-[var(--fg-muted)]">
              Nothing changed between these two versions.
            </p>
          )}

          {diff.unchanged > 0 && (
            <Button
              variant="ghost"
              onClick={() => setShowUnchanged((value) => !value)}
              className="mt-2 px-0 text-sm"
              aria-expanded={showUnchanged}
            >
              {showUnchanged
                ? "Hide unchanged sections"
                : `Show ${diff.unchanged} unchanged section${diff.unchanged === 1 ? "" : "s"}`}
            </Button>
          )}
        </>
      )}
    </section>
  );
}

const TONE: Record<
  string,
  { icon: typeof Plus; badge: string; label: string }
> = {
  added: { icon: Plus, badge: "success", label: "Added" },
  removed: { icon: Minus, badge: "destructive", label: "Removed" },
  rewritten: { icon: PencilLine, badge: "warning", label: "Rewritten" },
  reworded: { icon: PencilLine, badge: "secondary", label: "Edited" },
  unchanged: { icon: PencilLine, badge: "outline", label: "Unchanged" },
};

function ChangeRow({ change }: { change: VersionDiff["changes"][number] }) {
  const tone = TONE[change.change] ?? TONE.unchanged;
  const Icon = tone.icon;

  return (
    <div className="rounded-[var(--radius-md)] border border-[var(--border-default)] bg-[var(--bg-surface)] px-4 py-3">
      <div className="flex flex-wrap items-center gap-2">
        <Icon
          className="h-4 w-4 shrink-0 text-[var(--fg-muted)]"
          aria-hidden="true"
        />
        <span className="text-sm font-medium text-[var(--fg-default)]">
          {change.section ?? "The opening section"}
        </span>
        <Badge
          variant={
            tone.badge as
              "success" | "destructive" | "warning" | "secondary" | "outline"
          }
        >
          {tone.label}
        </Badge>
      </div>

      <p className="mt-1 text-sm text-[var(--fg-muted)]">{change.summary}</p>

      {/* The wording itself, both sides where both exist. A reviewer
          deciding whether an approval survives is deciding about these
          words, so they are on the page rather than behind a click. */}
      {change.change !== "unchanged" && (
        <div className="mt-3 flex flex-col gap-2">
          {change.previous_text && (
            <Passage label="Before" text={change.previous_text} muted />
          )}
          {change.current_text && (
            <Passage label="After" text={change.current_text} />
          )}
        </div>
      )}
    </div>
  );
}

function Passage({
  label,
  text,
  muted = false,
}: {
  label: string;
  text: string;
  muted?: boolean;
}) {
  return (
    <div>
      <span className="text-xs font-medium uppercase tracking-wide text-[var(--fg-subtle)]">
        {label}
      </span>
      <p
        className={`mt-0.5 whitespace-pre-wrap text-sm ${
          muted
            ? "text-[var(--fg-subtle)] line-through"
            : "text-[var(--fg-default)]"
        }`}
      >
        {text}
      </p>
    </div>
  );
}

/** The version immediately before this one, which is what a reader
 * almost always means by "what changed". */
function pickPrevious(
  versions: DocumentVersion[],
  currentFileId: string,
): DocumentVersion | null {
  const index = versions.findIndex(
    (version) => version.file_id === currentFileId,
  );
  if (index > 0) return versions[index - 1];
  // Reading the oldest version: the only comparison available is forward.
  return versions.find((version) => version.file_id !== currentFileId) ?? null;
}
