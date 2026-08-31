"use client";

import Link from "next/link";
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { FileClock, GitBranch, History, Info } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ApiError, apiFetch } from "@/lib/api";
import type { DocumentVersion, VersionCandidate } from "@/lib/types";

/** The version question, asked once, in the reader's words.
 *
 * Veyntra works out that an upload is a new version of a document it
 * already holds. It does not act on that alone. The link changes what
 * counts as current evidence and whose approvals survive, so it is
 * proposed here with the reasons that produced it and settled by a
 * person — and the alternative, "these are two documents", is a button
 * of equal weight rather than a way to dismiss a notice.
 */
export function VersionBanner({
  documentId,
  candidate,
  onDecided,
}: {
  documentId: string;
  candidate: VersionCandidate;
  onDecided?: () => void;
}) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);

  // `apiFetch` serializes the body itself — stringifying here would
  // send a JSON string where the API expects an object.
  const settle = (path: string, body?: Record<string, unknown>) =>
    apiFetch(`/api/v1/compliance/documents/${documentId}/${path}`, {
      method: "POST",
      body,
    });

  const decide = useMutation({
    mutationFn: (choice: "version" | "separate") =>
      choice === "version"
        ? settle("accept-version", {
            supersedes_file_id: candidate.file_id,
            version_label: candidate.detected_version,
          })
        : settle("separate-document"),
    onMutate: () => setError(null),
    onSuccess: async () => {
      // Both outcomes move evidence, coverage and the library, so the
      // whole compliance surface is refetched rather than the one query
      // that happens to be on screen.
      await queryClient.invalidateQueries({ queryKey: ["compliance"] });
      onDecided?.();
    },
    onError: (cause) =>
      setError(
        cause instanceof ApiError
          ? cause.message
          : "That did not go through. Nothing was changed.",
      ),
  });

  return (
    <section
      aria-labelledby="version-question"
      className="rounded-[var(--radius-lg)] border border-[var(--border-strong)] bg-[var(--bg-subtle)] p-5"
    >
      <div className="flex items-start gap-3">
        <GitBranch
          className="mt-0.5 h-5 w-5 shrink-0 text-[var(--fg-muted)]"
          aria-hidden="true"
        />
        <div className="min-w-0 flex-1">
          <h2
            id="version-question"
            className="text-sm font-semibold text-[var(--fg-default)]"
          >
            Is this a new version of {candidate.title}?
          </h2>
          <p className="mt-1 text-sm text-[var(--fg-muted)]">
            {candidate.confidence === "high"
              ? "This looks like a revision of a document you already have."
              : "This might be a revision of a document you already have."}{" "}
            Nothing has been linked yet.
          </p>

          {/* Both sides, side by side. The reader decides from what the
              two documents say about themselves — a similarity score is
              not something anybody can check, and the version numbers
              and dates are. */}
          <dl className="mt-4 grid gap-3 sm:grid-cols-2">
            <SideOfTheComparison
              heading="What you have"
              name={candidate.title}
              filename={candidate.current_filename}
              version={candidate.current_version}
              date={candidate.current_effective_date}
              approvedAt={candidate.current_approved_at}
            />
            <SideOfTheComparison
              heading="What you uploaded"
              name={candidate.uploaded_filename ?? "This document"}
              filename={null}
              version={candidate.detected_version}
              date={candidate.detected_effective_date}
              approvedAt={null}
            />
          </dl>

          {candidate.reasons.length > 0 && (
            <ul className="mt-3 flex flex-col gap-1">
              {candidate.reasons.map((reason) => (
                <li
                  key={reason}
                  className="flex items-start gap-2 text-sm text-[var(--fg-muted)]"
                >
                  <span
                    aria-hidden="true"
                    className="mt-2 h-1 w-1 shrink-0 rounded-full bg-[var(--fg-subtle)]"
                  />
                  {reason}
                </li>
              ))}
            </ul>
          )}

          <p className="mt-3 flex items-start gap-2 text-xs text-[var(--fg-subtle)]">
            <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
            Linking it keeps the older version and its history. Evidence whose
            wording did not change keeps its approval; evidence whose wording
            changed goes back for review.
          </p>

          <div className="mt-4 flex flex-wrap gap-2">
            <Button
              onClick={() => decide.mutate("version")}
              disabled={decide.isPending}
              aria-label={`Use as a new version of ${candidate.title}`}
            >
              {decide.isPending ? "Working…" : "Use as new version"}
            </Button>
            <Button
              variant="outline"
              onClick={() => decide.mutate("separate")}
              disabled={decide.isPending}
            >
              Treat as separate document
            </Button>
          </div>

          {error && (
            <p role="alert" className="mt-3 text-sm text-[var(--fg-danger)]">
              {error}
            </p>
          )}
        </div>
      </div>
    </section>
  );
}

/** One side of the version comparison.
 *
 * Only what the document actually states. A document with no version
 * number has no version number, and printing "Version 1" over it would
 * be putting words in its mouth in the one place a reader is deciding
 * whether to trust what it says.
 */
function SideOfTheComparison({
  heading,
  name,
  filename,
  version,
  date,
  approvedAt,
}: {
  heading: string;
  name: string;
  filename: string | null;
  version: string | null;
  date: string | null;
  approvedAt: string | null;
}) {
  return (
    <div className="rounded-[var(--radius-md)] border border-[var(--border-default)] bg-[var(--bg-surface)] px-3 py-2">
      <dt className="text-xs font-medium uppercase tracking-wide text-[var(--fg-subtle)]">
        {heading}
      </dt>
      <dd className="mt-1">
        <span className="block truncate text-sm font-medium text-[var(--fg-default)]">
          {name}
        </span>
        {filename && filename !== name && (
          <span className="block truncate text-xs text-[var(--fg-subtle)]">
            {filename}
          </span>
        )}
        <span className="mt-1 block text-sm text-[var(--fg-muted)]">
          {version ? `Version ${version}` : "No version stated"}
        </span>
        {date && (
          <span className="block text-sm text-[var(--fg-muted)]">
            Effective {date}
          </span>
        )}
        {approvedAt && (
          <span className="block text-sm text-[var(--fg-muted)]">
            Approved {formatUploadDate(approvedAt)}
          </span>
        )}
      </dd>
    </div>
  );
}

/** You are reading a version that has been replaced.
 *
 * A Copilot citation made months ago points at the wording that was
 * actually cited, and it must keep doing so — rewriting old citations to
 * land on current text would quietly falsify the record. What the reader
 * needs instead is to know where they are and one click to the version
 * the organization is held to today.
 */
export function SupersededNotice({
  currentHref,
  currentLabel,
}: {
  currentHref: string | null;
  currentLabel: string | null;
}) {
  return (
    <div
      role="note"
      className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-[var(--radius-lg)] border border-[var(--border-default)] bg-[var(--bg-subtle)] px-4 py-3"
    >
      <History
        className="h-4 w-4 shrink-0 text-[var(--fg-muted)]"
        aria-hidden="true"
      />
      <span className="text-sm text-[var(--fg-default)]">
        You are reading an earlier version of this document. It is kept for the
        record and is not what your organization is held to now.
      </span>
      {currentHref && (
        <Link
          href={currentHref}
          className="text-sm font-medium text-[var(--fg-accent)] underline underline-offset-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--border-focus)]"
        >
          Go to the current version{currentLabel ? ` (${currentLabel})` : ""}
        </Link>
      )}
    </div>
  );
}

/** Every version of this document, newest first.
 *
 * Superseded versions stay reachable and readable. A citation made
 * against wording that has since been rewritten still opens the words
 * that were actually cited — swapping in the current text would quietly
 * rewrite history in a product whose job is to keep it.
 */
export function VersionHistory({
  versions,
  currentFileId,
}: {
  versions: DocumentVersion[];
  currentFileId: string;
}) {
  if (versions.length < 2) return null;

  const newestFirst = [...versions].reverse();

  return (
    <section aria-labelledby="version-history" className="mt-8">
      <h2
        id="version-history"
        className="flex items-center gap-2 text-sm font-semibold text-[var(--fg-default)]"
      >
        <FileClock
          className="h-4 w-4 text-[var(--fg-muted)]"
          aria-hidden="true"
        />
        Version history
        <span className="font-normal text-[var(--fg-subtle)]">
          {versions.length} versions
        </span>
      </h2>

      <ol className="mt-3 flex flex-col gap-2">
        {newestFirst.map((version, index) => {
          const isThisPage = version.file_id === currentFileId;
          const label =
            version.version_label ??
            (version.status === "current"
              ? "Current version"
              : `Version ${newestFirst.length - index}`);

          return (
            <li key={version.file_id}>
              <VersionRow
                version={version}
                label={label}
                isThisPage={isThisPage}
              />
            </li>
          );
        })}
      </ol>
    </section>
  );
}

function VersionRow({
  version,
  label,
  isThisPage,
}: {
  version: DocumentVersion;
  label: string;
  isThisPage: boolean;
}) {
  const body = (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
      <span className="text-sm font-medium text-[var(--fg-default)]">
        {label}
      </span>
      {version.status === "current" ? (
        <Badge variant="success">Current</Badge>
      ) : (
        <Badge variant="outline">Superseded</Badge>
      )}
      {isThisPage && (
        <span className="text-xs text-[var(--fg-subtle)]">You are here</span>
      )}
      <span className="text-xs text-[var(--fg-subtle)]">
        Uploaded {formatUploadDate(version.uploaded_at)}
      </span>
      <span className="text-xs text-[var(--fg-subtle)]">
        {version.evidence_count === 1
          ? "1 piece of evidence"
          : `${version.evidence_count} pieces of evidence`}
      </span>
    </div>
  );

  const shell =
    "block rounded-[var(--radius-md)] border border-[var(--border-default)] bg-[var(--bg-surface)] px-4 py-3";

  // A version with no readable page is still listed — it is part of the
  // history — but it is not a link that goes nowhere.
  if (!version.href || isThisPage) {
    return <div className={shell}>{body}</div>;
  }

  return (
    <Link
      href={version.href}
      className={`${shell} transition-colors hover:border-[var(--border-strong)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--border-focus)]`}
    >
      {body}
    </Link>
  );
}

function formatUploadDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "at an unknown time";
  return date.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}
