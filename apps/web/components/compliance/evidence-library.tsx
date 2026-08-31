"use client";

import Link from "next/link";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, FileText, Quote } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { apiFetch } from "@/lib/api";
import type { GroupedEvidence } from "@/lib/types";

/** Evidence grouped by the document it came from.
 *
 * This used to render one card per evidence row, so a policy mapped to
 * six controls appeared as six identical filenames — which reads as six
 * documents. The mappings are unchanged; only the shape is. What a person
 * needs to understand is one document → several statements → several
 * controls, and a flat list actively hides that.
 */
export function EvidenceLibrary() {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const { data: documents } = useQuery<GroupedEvidence[]>({
    queryKey: ["compliance", "evidence-by-document"],
    queryFn: () => apiFetch<GroupedEvidence[]>("/api/v1/compliance/evidence/by-document"),
  });

  const toggle = (fileId: string) =>
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(fileId)) next.delete(fileId);
      else next.add(fileId);
      return next;
    });

  return (
    <div className="mb-8">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
        Evidence Library
      </h2>

      {documents?.length === 0 && (
        <p className="text-sm text-[var(--fg-muted)]">
          No evidence yet. Upload a document under Documents and Veyntra will propose which
          controls it evidences.
        </p>
      )}

      <div className="flex flex-col gap-2">
        {(documents ?? []).map((document) => {
          const open = expanded.has(document.file_id);
          return (
            <Card key={document.file_id}>
              <CardContent className="py-4">
                <button
                  type="button"
                  onClick={() => toggle(document.file_id)}
                  aria-expanded={open}
                  className="flex w-full items-start justify-between gap-3 text-left"
                >
                  <span className="min-w-0">
                    <span className="flex items-center gap-2 font-medium text-[var(--fg-default)]">
                      {open ? (
                        <ChevronDown className="h-4 w-4 shrink-0" aria-hidden="true" />
                      ) : (
                        <ChevronRight className="h-4 w-4 shrink-0" aria-hidden="true" />
                      )}
                      <FileText
                        className="h-4 w-4 shrink-0 text-[var(--fg-subtle)]"
                        aria-hidden="true"
                      />
                      {document.title || document.filename}
                    </span>
                    <span className="mt-1 block pl-10 text-sm text-[var(--fg-muted)]">
                      {document.evidence_count} evidence item
                      {document.evidence_count === 1 ? "" : "s"} · mapped to{" "}
                      {document.control_count} control
                      {document.control_count === 1 ? "" : "s"}
                    </span>
                  </span>
                  <span className="flex shrink-0 flex-wrap items-center gap-1.5">
                    {document.document_domain && (
                      <Badge variant="outline">{document.document_domain}</Badge>
                    )}
                    {document.processing_status === "ready" && (
                      <Badge variant="success">Analyzed</Badge>
                    )}
                  </span>
                </button>

                {/* Outside the disclosure button, because a link nested
                    in a button is neither. The row's own action is
                    expand; opening the document is its own control. */}
                {document.document_href && (
                  <Link
                    href={document.document_href}
                    className="mt-1 inline-flex items-center gap-1.5 pl-10 text-sm text-[var(--brand-primary)] hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--border-focus)]"
                  >
                    Open document
                    <ChevronRight className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                  </Link>
                )}

                {open && (
                  <div className="mt-3 flex flex-col gap-3 border-t border-[var(--border-default)] pt-3">
                    {document.mappings.map((mapping, index) => (
                      <div key={mapping.evidence_id} className="pl-10">
                        <p className="text-sm text-[var(--fg-subtle)]">
                          Mapping {index + 1} of {document.mappings.length}
                        </p>
                        {/* Every value says what it is. A bare badge
                            reading "4. Confidentiality and security" could
                            be a document section, a control, or a
                            requirement — three different things, and the
                            reader had to guess which. A definition list
                            says it in the markup as well as on screen. */}
                        <dl className="mt-1 grid grid-cols-[max-content_1fr] gap-x-3 gap-y-1 text-sm">
                          <dt className="text-[var(--fg-subtle)]">Mapped control</dt>
                          <dd className="font-medium text-[var(--fg-default)]">
                            {mapping.control_title}
                          </dd>
                          {mapping.source_location && (
                            <>
                              <dt className="text-[var(--fg-subtle)]">Source section</dt>
                              <dd className="text-[var(--fg-muted)]">
                                {mapping.source_location}
                              </dd>
                            </>
                          )}
                          {mapping.evidence_type && (
                            <>
                              <dt className="text-[var(--fg-subtle)]">Evidence type</dt>
                              <dd className="text-[var(--fg-muted)]">
                                {mapping.evidence_type.replace(/_/g, " ")}
                              </dd>
                            </>
                          )}
                          {mapping.confidence !== null && (
                            <>
                              <dt className="text-[var(--fg-subtle)]">Match confidence</dt>
                              <dd className="text-[var(--fg-muted)]">
                                {Math.round(mapping.confidence * 100)}%
                              </dd>
                            </>
                          )}
                          <dt className="text-[var(--fg-subtle)]">Mapped by</dt>
                          <dd className="text-[var(--fg-muted)]">
                            {mapping.mapped_by === "auto"
                              ? "Veyntra, accepted automatically"
                              : mapping.mapped_by === "human"
                                ? "Veyntra, approved by a person"
                                : "Attached by a person"}
                          </dd>
                        </dl>
                        {mapping.quoted_passage && (
                          <blockquote
                            className="mt-2 flex gap-2 border-l-2 border-[var(--brand-primary)] bg-[var(--bg-app)] p-2"
                            aria-label="Passage quoted from the document"
                          >
                            <Quote
                              className="mt-0.5 h-3 w-3 shrink-0 text-[var(--fg-subtle)]"
                              aria-hidden="true"
                            />
                            <p className="text-sm italic leading-relaxed text-[var(--fg-default)]">
                              {mapping.quoted_passage}
                            </p>
                          </blockquote>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
