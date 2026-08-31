import Link from "next/link";
import { ChevronDown, Database, FileText } from "lucide-react";

import type { Citation, ComplianceFact } from "@/lib/types";

/** Where a Copilot answer came from — two provenances, never merged.
 *
 * The old citation read `Document da7966ef · chunk 5`. A UUID is a
 * primary key and a chunk number is an artefact of slicing a file into
 * 1000-character windows; neither is findable in the customer's own copy
 * of the document, which is the only thing a citation is for. Every
 * citation now arrives already resolved to a title, a heading and a page.
 *
 * `facts` and `citations` are rendered as separate blocks because they
 * answer different questions. "Current status: Needs review" is a
 * determination Veyntra made from declared facts and evidence — putting
 * it under a document citation would claim an uploaded PDF said it.
 */

/** Above this, an answer is long enough that five expanded sources push
 * it off the screen — so Sources starts collapsed. A two-line answer with
 * its sources already open reads as one thing, which is better. */
export const LONG_ANSWER_CHARS = 400;

export function ComplianceFacts({ facts }: { facts: ComplianceFact[] }) {
  if (facts.length === 0) return null;

  return (
    <section className="mt-3 rounded-[var(--radius-md)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-3">
      <h3 className="flex items-center gap-1.5 text-xs font-medium text-[var(--fg-muted)]">
        <Database className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
        From your Veyntra records
      </h3>
      <dl className="mt-2 flex flex-col gap-2">
        {facts.map((fact) => (
          <div key={`${fact.label}-${fact.value}`}>
            <div className="flex flex-wrap items-baseline gap-x-2">
              <dt className="text-xs text-[var(--fg-subtle)]">{fact.label}</dt>
              <dd className="text-sm font-medium text-[var(--fg-default)]">{fact.value}</dd>
            </div>
            {fact.detail && (
              <p className="mt-0.5 text-xs text-[var(--fg-subtle)]">{fact.detail}</p>
            )}
          </div>
        ))}
      </dl>
      {/* Said plainly, because the distinction is the point. */}
      <p className="mt-2 text-[11px] leading-relaxed text-[var(--fg-subtle)]">
        Read from your compliance data, not from an uploaded document.
      </p>
    </section>
  );
}

export function CopilotSources({
  citations,
  answerLength,
}: {
  citations: Citation[];
  answerLength: number;
}) {
  if (citations.length === 0) return null;

  return (
    <details
      className="group mt-3 rounded-[var(--radius-md)] border border-[var(--border-default)] bg-[var(--bg-surface)]"
      open={answerLength <= LONG_ANSWER_CHARS}
    >
      {/* A native disclosure: keyboard-operable and announced as expanded
          or collapsed without any state of our own. */}
      <summary className="flex cursor-pointer list-none items-center gap-1.5 rounded-[var(--radius-md)] px-3 py-2 text-xs font-medium text-[var(--fg-muted)] hover:text-[var(--fg-default)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--border-focus)]">
        <ChevronDown
          className="h-3.5 w-3.5 shrink-0 transition-transform group-open:rotate-180"
          aria-hidden="true"
        />
        Sources ({citations.length})
      </summary>

      <ul className="flex flex-col gap-2 px-3 pb-3">
        {citations.map((citation) => (
          <li
            key={`${citation.document_id}-${citation.section ?? ""}-${citation.page ?? ""}`}
            className="rounded-[var(--radius-md)] border border-[var(--border-default)] bg-[var(--bg-app)] p-2.5"
          >
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
              {/* The server's href, verbatim. Building one here from
                  `document_id` is what produced links into `/knowledge`,
                  a module the middleware 404s. */}
              <Link
                href={citation.href}
                className="inline-flex items-center gap-1.5 rounded-sm text-xs font-medium text-[var(--fg-default)] hover:text-[var(--brand-primary)] hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--border-focus)]"
              >
                <FileText className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                {citation.reference}
              </Link>
              {citation.source_type && (
                <span className="rounded-[var(--radius-sm)] bg-[var(--gray-100)] px-1.5 py-0.5 text-[11px] text-[var(--fg-subtle)]">
                  {citation.source_type}
                </span>
              )}
            </div>
            {citation.passage && (
              <blockquote className="mt-1.5 border-l-2 border-[var(--border-default)] pl-2 text-xs leading-relaxed text-[var(--fg-muted)]">
                {citation.passage}
              </blockquote>
            )}
          </li>
        ))}
      </ul>
    </details>
  );
}

/* There is deliberately no `documentHref` helper here any more.
 *
 * There was one, and before that the panel inlined
 * `/knowledge/${citation.document_id}`, which the middleware rewrote to a
 * 404 once that module was retired. Every href now arrives on the
 * citation, composed by app/ai/citations.py, so a route change happens in
 * one place and cannot be missed here. */
