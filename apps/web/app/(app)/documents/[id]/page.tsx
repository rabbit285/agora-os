"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, use, useEffect, useMemo, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, ShieldCheck, Sparkles } from "lucide-react";

import { UploadNewVersion } from "@/components/documents/upload-version";
import { VersionCompare } from "@/components/documents/version-compare";
import {
  SupersededNotice,
  VersionBanner,
  VersionHistory,
} from "@/components/documents/version-panel";
import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { apiFetch } from "@/lib/api";
import { assembleSections, findPassage } from "@/lib/document-text";
import type {
  DocumentChunk,
  DocumentDetail,
  DocumentEvidence,
} from "@/lib/types";

/** One document, one page.
 *
 * The canonical Document Detail route. A row in the document library and
 * a Copilot citation both open it — the library at the top, the citation
 * at the passage it cited. There is deliberately no second viewer: the
 * chunk dump at /knowledge/[id] is for inspecting the index and has been
 * behind a middleware 404 since that module was withdrawn, which is why
 * citations pointing at it rendered as "Document da7966ef · chunk 3" and
 * opened nothing.
 */
export default function DocumentDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  // `useSearchParams` needs a boundary above it; the citation's passage
  // arrives in the query string, so the reader is what suspends.
  return (
    <Suspense fallback={null}>
      <DocumentReader id={id} />
    </Suspense>
  );
}

function DocumentReader({ id }: { id: string }) {
  const search = useSearchParams();
  const passage = search.get("passage") ?? "";

  const { data: detail } = useQuery<DocumentDetail>({
    queryKey: ["compliance", "documents", id, "detail"],
    queryFn: () =>
      apiFetch<DocumentDetail>(`/api/v1/compliance/documents/${id}/detail`),
  });

  const { data: chunks } = useQuery<DocumentChunk[]>({
    queryKey: ["knowledge", "documents", id, "chunks"],
    queryFn: () =>
      apiFetch<DocumentChunk[]>(`/api/v1/knowledge/documents/${id}/chunks`),
    // Gated on whether the text was ingested, not on whether the
    // compliance analysis ran. They are separate pipelines, and gating
    // on the wrong one showed an empty page for a document the Copilot
    // was citing happily.
    enabled: detail?.content_status === "ready",
  });

  const sections = useMemo(() => assembleSections(chunks ?? []), [chunks]);

  // Only one section carries the passage. Found once here rather than in
  // each section, so a phrase that happens to recur is highlighted where
  // the citation meant it, not everywhere it appears.
  const highlightIndex = useMemo(() => {
    if (!passage) return -1;
    return sections.findIndex(
      (section) => findPassage(section.text, passage) !== null,
    );
  }, [sections, passage]);

  if (!detail) return null;

  // Reading history. The version being looked at is not the one the
  // organization is currently held to, and every action on this page has
  // to say so rather than quietly acting on the current version instead.
  const isSuperseded = detail.versions.some(
    (version) =>
      version.file_id === detail.file_id && version.status === "superseded",
  );
  const current =
    detail.versions.find((version) => version.status === "current") ?? null;

  return (
    <div>
      <PageHeader
        title={detail.title}
        description={
          passage
            ? "Opened at the passage cited by your Copilot."
            : detail.filename
        }
        actions={
          <div className="flex flex-wrap items-start gap-2">
            {/* The explicit path, for a rewrite so thorough that
                detection would not recognise it. Offered only on the
                current version: replacing a superseded one would fork
                the chain. */}
            {!isSuperseded && (
              <UploadNewVersion
                supersedesFileId={detail.file_id}
                documentTitle={detail.title}
              />
            )}
            {/* A plain link, so browser Back still returns wherever the
                reader came from — the library, or the Copilot. */}
            <Link
              href="/documents"
              className="inline-flex items-center gap-1.5 rounded-[var(--radius-md)] border border-[var(--border-default)] px-3 py-1.5 text-sm text-[var(--fg-muted)] hover:text-[var(--fg-default)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--border-focus)]"
            >
              <ArrowLeft className="h-4 w-4" aria-hidden="true" />
              All documents
            </Link>
          </div>
        }
      />

      {isSuperseded && (
        <div className="mb-6">
          <SupersededNotice
            currentHref={current?.href ?? null}
            currentLabel={current?.version_label ?? null}
          />
        </div>
      )}

      {/* Asked before the document is read, not after: whether these
          are one document or two changes what the reader is looking at. */}
      {detail.version_candidate && (
        <div className="mb-6">
          <VersionBanner documentId={id} candidate={detail.version_candidate} />
        </div>
      )}

      <div className="flex flex-col gap-6 lg:flex-row lg:items-start">
        <div className="min-w-0 flex-1">
          <DocumentContent
            detail={detail}
            sections={sections}
            passage={passage}
            highlightIndex={highlightIndex}
            hasChunks={(chunks?.length ?? 0) > 0}
          />
        </div>

        <aside className="flex w-full shrink-0 flex-col gap-4 lg:w-80">
          <AboutDocument detail={detail} />
          <Analysis detail={detail} />
          <PolicyGovernance detail={detail} />
        </aside>
      </div>

      <EvidenceExtracted evidence={detail.evidence} />

      <VersionCompare
        documentId={id}
        versions={detail.versions}
        currentFileId={detail.file_id}
      />

      <VersionHistory
        versions={detail.versions}
        currentFileId={detail.file_id}
      />
    </div>
  );
}

/* ------------------------------------------------------------------ */

function DocumentContent({
  detail,
  sections,
  passage,
  highlightIndex,
  hasChunks,
}: {
  detail: DocumentDetail;
  sections: ReturnType<typeof assembleSections>;
  passage: string;
  highlightIndex: number;
  hasChunks: boolean;
}) {
  if (detail.content_status !== "ready") {
    return (
      <EmptyState
        title="This document is not readable yet"
        description={
          detail.content_error ??
          detail.processing_error ??
          "Veyntra is still reading it. Its text appears here once processing finishes."
        }
      />
    );
  }

  if (!hasChunks) {
    return (
      <EmptyState
        title="No text to show"
        description={
          detail.index_error ??
          "This document was analysed but its text is not available to read here."
        }
      />
    );
  }

  return (
    <article className="flex flex-col gap-6 rounded-[var(--radius-lg)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-6">
      {sections.map((section, index) => (
        <Section
          key={`${section.label ?? "body"}-${index}`}
          label={section.label}
          page={section.page}
          text={section.text}
          passage={index === highlightIndex ? passage : ""}
        />
      ))}
    </article>
  );
}

function Section({
  label,
  page,
  text,
  passage,
}: {
  label: string | null;
  page: number | null;
  text: string;
  passage: string;
}) {
  return (
    <section>
      {label && (
        <h2 className="mb-2 text-sm font-semibold text-[var(--fg-default)]">
          {label}
          {page !== null && (
            <span className="ml-2 font-normal text-[var(--fg-subtle)]">
              page {page}
            </span>
          )}
        </h2>
      )}
      <Passage text={text} passage={passage} />
    </section>
  );
}

function Passage({ text, passage }: { text: string; passage: string }) {
  const marked = useRef<HTMLElement>(null);
  const range = passage ? findPassage(text, passage) : null;

  useEffect(() => {
    // Scrolled after paint, so the reader arrives at the passage rather
    // than at the top of a document they then have to search. Without a
    // passage there is no mark, nothing scrolls, and the page opens at
    // the top — which is what arriving from the library should do.
    marked.current?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [passage]);

  if (!range) {
    return (
      <p className="whitespace-pre-wrap text-sm leading-relaxed text-[var(--fg-muted)]">
        {text}
      </p>
    );
  }

  return (
    <p className="whitespace-pre-wrap text-sm leading-relaxed text-[var(--fg-muted)]">
      {text.slice(0, range.start)}
      {/* Tinted with color-mix rather than a fixed light shade so the
          highlight works on the dark surface too — a pale teal block with
          the theme's near-white text on it is unreadable. */}
      <mark
        ref={marked}
        tabIndex={-1}
        className="rounded-sm bg-[color-mix(in_srgb,var(--ai-500)_28%,transparent)] px-0.5 text-[var(--fg-default)]"
      >
        {/* Not colour alone: the highlight says what it is out loud. */}
        <span className="sr-only">Start of cited passage. </span>
        {text.slice(range.start, range.end)}
        <span className="sr-only"> End of cited passage.</span>
      </mark>
      {text.slice(range.end)}
    </p>
  );
}

/* ------------------------------------------------------------------ */

/** What this document is. One list of facts, each labelled — so nobody
 * has to work out whether "Analyzed" refers to the reading or to the
 * indexing, which are separate pipelines that fail separately. */
function AboutDocument({ detail }: { detail: DocumentDetail }) {
  const rows: { label: string; value: React.ReactNode }[] = [
    { label: "Filename", value: detail.filename },
  ];
  if (detail.document_type)
    rows.push({ label: "Document type", value: detail.document_type });
  if (detail.document_domain)
    rows.push({ label: "Category", value: detail.document_domain });
  rows.push({
    label: "Processing",
    value: <ProcessingBadge status={detail.processing_status} />,
  });
  rows.push({
    label: "Copilot",
    value: <IndexBadge status={detail.index_status} />,
  });
  if (detail.extracted_characters !== null) {
    rows.push({
      label: "Text read",
      value: `${detail.extracted_characters.toLocaleString()} characters`,
    });
  }

  return (
    <Card>
      <CardContent className="pt-6">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
          About this document
        </h2>
        <dl className="flex flex-col gap-2">
          {rows.map((row) => (
            <div
              key={row.label}
              className="flex flex-wrap items-baseline justify-between gap-2"
            >
              <dt className="text-xs text-[var(--fg-subtle)]">{row.label}</dt>
              <dd className="min-w-0 break-words text-right text-sm text-[var(--fg-default)]">
                {row.value}
              </dd>
            </div>
          ))}
        </dl>
      </CardContent>
    </Card>
  );
}

function ProcessingBadge({ status }: { status: string }) {
  if (status === "ready") return <Badge variant="success">Analyzed</Badge>;
  if (status === "failed" || status === "unsupported") {
    return (
      <Badge variant="destructive">
        {status === "unsupported" ? "Cannot read" : "Failed"}
      </Badge>
    );
  }
  if (status === "not_analyzed")
    return <Badge variant="outline">Not analyzed</Badge>;
  return <Badge variant="outline">Reading</Badge>;
}

function IndexBadge({ status }: { status: string }) {
  if (status === "indexed") {
    return (
      <Badge variant="secondary" className="gap-1">
        <Sparkles className="h-3 w-3" aria-hidden="true" />
        Indexed
      </Badge>
    );
  }
  if (status === "pending") return <Badge variant="outline">Indexing</Badge>;
  return <Badge variant="destructive">Not available</Badge>;
}

/** What the analysis found, as three numbers that mean three different
 * things: passages, the controls they support, the requirements behind
 * those controls. */
function Analysis({ detail }: { detail: DocumentDetail }) {
  const metrics = [
    {
      value: detail.evidence_count,
      label: detail.evidence_count === 1 ? "evidence item" : "evidence items",
    },
    {
      value: detail.control_count,
      label: detail.control_count === 1 ? "control" : "controls",
    },
    {
      value: detail.requirement_count,
      label:
        detail.requirement_count === 1
          ? "framework requirement"
          : "framework requirements",
    },
  ];

  return (
    <Card>
      <CardContent className="pt-6">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
          Analysis
        </h2>
        {detail.evidence_count === 0 ? (
          <p className="text-sm text-[var(--fg-muted)]">
            Veyntra read this document and proposed no control matches.
          </p>
        ) : (
          <dl className="flex flex-col gap-1.5">
            {metrics.map((metric) => (
              <div key={metric.label} className="flex items-baseline gap-2">
                <dd className="text-lg font-semibold leading-none text-[var(--fg-default)]">
                  {metric.value}
                </dd>
                <dt className="text-sm text-[var(--fg-muted)]">
                  {metric.label}
                </dt>
              </div>
            ))}
          </dl>
        )}
        {detail.proposed_count > 0 && (
          <p className="mt-3 text-sm text-[var(--warning-700)]">
            {detail.proposed_count} awaiting your review
          </p>
        )}
        {detail.unverifiable_count > 0 && (
          <p className="mt-1 text-xs text-[var(--fg-subtle)]">
            {detail.unverifiable_count} discarded as unverifiable
          </p>
        )}
      </CardContent>
    </Card>
  );
}

/** The governance record, when this document is a policy.
 *
 * A link, not an editor. Approving a policy, scheduling its review and
 * naming its owner already have a screen that does them properly, and
 * two places to do the same thing is how they end up disagreeing. */
function PolicyGovernance({ detail }: { detail: DocumentDetail }) {
  if (!detail.policy_id) return null;

  return (
    <Card>
      <CardContent className="pt-6">
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
          Policy governance
        </h2>
        <p className="font-medium text-[var(--fg-default)]">
          {detail.policy_title}
        </p>
        <p className="mt-1 text-sm text-[var(--fg-muted)]">
          {detail.policy_status === "approved"
            ? "Approved"
            : "Needs governance review"}
        </p>
        <Link
          href={`/compliance/policies/${detail.policy_id}`}
          className="mt-3 inline-flex items-center gap-1.5 text-sm text-[var(--brand-primary)] hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--border-focus)]"
        >
          <ShieldCheck className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          Open policy
        </Link>
      </CardContent>
    </Card>
  );
}

/** Document → passage → control → requirement, on one row each.
 *
 * The chain is the point. A reader looking at "6 evidence items" needs to
 * be able to ask which parts of the document those were and what they
 * support, without going to three other screens to find out. */
function EvidenceExtracted({ evidence }: { evidence: DocumentEvidence[] }) {
  const shown = evidence.filter((item) => item.status !== "unverifiable");
  if (shown.length === 0) return null;

  return (
    <section className="mt-6">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
        Evidence extracted
      </h2>
      <ul className="flex flex-col gap-2">
        {shown.map((item) => (
          <li key={item.id}>
            <Card>
              <CardContent className="py-4">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="font-medium text-[var(--fg-default)]">
                      {item.source_location ?? "Whole document"}
                    </p>
                    {item.control_title && (
                      <p className="mt-1 text-sm text-[var(--fg-muted)]">
                        <span aria-hidden="true">→ </span>
                        {item.control_id ? (
                          <Link
                            href={`/compliance/controls/${item.control_id}`}
                            className="hover:text-[var(--brand-primary)] hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--border-focus)]"
                          >
                            {item.control_title}
                          </Link>
                        ) : (
                          item.control_title
                        )}
                      </p>
                    )}
                    {item.requirement_reference && (
                      <p className="mt-0.5 text-sm text-[var(--fg-muted)]">
                        <span aria-hidden="true">→ </span>
                        {[item.framework_name, item.requirement_reference]
                          .filter(Boolean)
                          .join(" ")}
                        {item.requirement_title &&
                          ` — ${item.requirement_title}`}
                      </p>
                    )}
                  </div>
                  <div className="flex shrink-0 flex-wrap items-center gap-1.5">
                    {item.confidence !== null && (
                      <span className="text-xs text-[var(--fg-subtle)]">
                        Confidence {Math.round(item.confidence * 100)}%
                      </span>
                    )}
                    <EvidenceStatusBadge status={item.status} />
                  </div>
                </div>
              </CardContent>
            </Card>
          </li>
        ))}
      </ul>
    </section>
  );
}

function EvidenceStatusBadge({ status }: { status: string }) {
  // "Proposed" and "Approved" are different claims about the same
  // passage, and flattening them is how unreviewed suggestions start
  // reading as compliance evidence.
  if (status === "approved" || status === "auto_approved") {
    return <Badge variant="success">Approved</Badge>;
  }
  if (status === "rejected") return <Badge variant="outline">Rejected</Badge>;
  return <Badge variant="warning">Awaiting review</Badge>;
}
