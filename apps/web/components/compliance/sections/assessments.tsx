"use client";

import Link from "next/link";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { NeedsSetupPanel } from "@/components/compliance/needs-setup";
import { CreateAuditForm } from "@/components/compliance/create-audit";
import { LifecycleMenu } from "@/components/compliance/lifecycle-menu";
import { LifecycleTabs } from "@/components/compliance/lifecycle-tabs";
import { Archive } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { StatusBadge } from "@/components/status-badge";
import { CreatePanel } from "@/components/create-panel";
import { EmptyState } from "@/components/empty-state";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { CARD_LINK_FOCUS } from "@/lib/focus";
import { looksLikeAQuestion } from "@/lib/questionnaire-title";
import { apiFetch } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import type {
  Audit,
  Questionnaire,
  QuestionnaireSource,
  SecurityReview,
} from "@/lib/types";

const selectClassName =
  "flex h-9 rounded-md border border-[var(--border-strong)] bg-[var(--bg-surface)] px-3 py-1 text-sm text-[var(--fg-default)] shadow-[var(--shadow-token-sm)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--border-focus)]";

/* Questionnaires, audits, and the security reviews customers send.
 *
 * "Enterprise Sales Security Reviews" was named for a sales module this
 * product no longer has. It is the same workflow — a customer asks how
 * you handle their data before they sign — so it keeps its data and
 * loses the CRM framing. */

/** "This one is in the archive", said once and plainly.
 *
 * A row carrying only its workflow status is ambiguous in the archive:
 * an archived draft and an active draft render identically, so a list of
 * drafts under "Archived" reads as a filter that is not working.
 * Lifecycle gets its own badge, ahead of the workflow one, so the two
 * dimensions are visibly different things rather than one competing to
 * describe the other.
 *
 * Never rendered on an active row — "not archived" is the ordinary case
 * and does not need saying.
 */
function ArchivedBadge() {
  return (
    <Badge variant="secondary" className="gap-1">
      <Archive className="h-3 w-3" aria-hidden="true" />
      Archived
    </Badge>
  );
}

/** When a record was put away, in the words a row has space for.
 *
 * Shown only in the archived list. Workflow status and lifecycle state
 * are different dimensions — an archived questionnaire is still a draft
 * — so a row that says only "draft" gives no clue which list it is in,
 * which is how an archived list full of drafts reads as a broken filter.
 */
function archivedOn(archivedAt: string | null): string | null {
  if (!archivedAt) return null;
  const date = new Date(archivedAt);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export function QuestionnairesSection() {
  const queryClient = useQueryClient();
  const [title, setTitle] = useState("");
  const [customer, setCustomer] = useState("");
  const [source, setSource] =
    useState<QuestionnaireSource>("internal_template");
  const [lifecycle, setLifecycle] = useState<"active" | "archived">("active");

  // Both lifecycle states, so the tab counts are the real totals rather
  // than a count of whatever happens to be on screen. Neither list is
  // paginated and both are small; the second query also makes switching
  // tabs instant instead of a spinner.
  const { data: active } = useQuery<Questionnaire[]>({
    queryKey: ["compliance", "questionnaires", { archived: false }],
    queryFn: () =>
      apiFetch<Questionnaire[]>(
        "/api/v1/compliance/questionnaires?archived=false",
      ),
  });
  const { data: archived } = useQuery<Questionnaire[]>({
    queryKey: ["compliance", "questionnaires", { archived: true }],
    queryFn: () =>
      apiFetch<Questionnaire[]>(
        "/api/v1/compliance/questionnaires?archived=true",
      ),
  });
  const showingArchived = lifecycle === "archived";
  const questionnaires = showingArchived ? archived : active;

  const fromCustomer = source === "customer_provided";
  // Asked for here, at the only moment anybody actually knows it. A
  // customer questionnaire created without a customer has no engagement
  // to belong to, and repairing that later means reading a name off a
  // title and hoping — which is how "Agora Origin cusotmer" nearly
  // became a customer record.
  const namedCustomer = customer.trim();
  const titleReadsLikeAQuestion = looksLikeAQuestion(title);

  const createQuestionnaire = useMutation({
    mutationFn: () =>
      apiFetch<Questionnaire>("/api/v1/compliance/questionnaires", {
        method: "POST",
        body: {
          title,
          source,
          customer_name: fromCustomer ? namedCustomer : null,
        },
      }),
    onSuccess: () => {
      setTitle("");
      setCustomer("");
      setSource("internal_template");
      queryClient.invalidateQueries({
        queryKey: ["compliance", "questionnaires"],
      });
      // The engagement list changes too: this may have opened one.
      queryClient.invalidateQueries({
        queryKey: ["compliance", "security-reviews"],
      });
    },
  });

  return (
    <div className="mb-10">
      {/* The section's action belongs to the section, not to whichever
          lifecycle tab happens to be open. Heading and create on one
          line, the filter on its own below it. */}
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
          Questionnaires
        </h2>
        <CreatePanel label="Create questionnaire">
          <div className="flex flex-col gap-2">
            <select
              className={`${selectClassName} w-full`}
              aria-label="Questionnaire type"
              value={source}
              onChange={(e) => setSource(e.target.value as QuestionnaireSource)}
            >
              <option value="internal_template">Internal assessment</option>
              <option value="customer_provided">
                Customer security questionnaire
              </option>
            </select>

            {fromCustomer && (
              <Input
                placeholder="Customer name — the company that sent it"
                aria-label="Customer"
                value={customer}
                onChange={(e) => setCustomer(e.target.value)}
              />
            )}

            <Input
              /* The placeholder follows the customer, so the shape of a
                 good title is visible without anything being filled in
                 on somebody's behalf. A suggestion in a real value is a
                 guess the product would then be storing. */
              placeholder={
                fromCustomer
                  ? `${namedCustomer || "Acme Corp"} Security Questionnaire`
                  : "Questionnaire title"
              }
              aria-label="Questionnaire title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />

            {/* A questionnaire is the document; a question is a line in
                it. Titling one "Do you encrypt customer data at rest?"
                reads as a single question and gives the review nothing to
                be called. Said, not enforced — somebody may have a reason,
                and a create button that refuses to explain itself is
                worse than a title nobody likes. */}
            {titleReadsLikeAQuestion && (
              <p className="text-xs text-[var(--warning-700)]">
                That looks like one of the questions rather than the name of
                the questionnaire. Something like &ldquo;
                {namedCustomer || "Acme"} Customer Security
                Questionnaire&rdquo; reads better everywhere it appears.
              </p>
            )}

            <div className="flex items-center gap-2">
              <Button
                disabled={
                  !title.trim() ||
                  (fromCustomer && !namedCustomer) ||
                  createQuestionnaire.isPending
                }
                onClick={() => createQuestionnaire.mutate()}
              >
                Create questionnaire
              </Button>
              {fromCustomer && (
                <span className="text-xs text-[var(--fg-subtle)]">
                  {namedCustomer
                    ? `Joins ${namedCustomer}'s security review.`
                    : "Name the customer so this joins their security review."}
                </span>
              )}
            </div>
          </div>
        </CreatePanel>
      </div>

      <div className="mb-4">
        <LifecycleTabs
          value={lifecycle}
          onChange={setLifecycle}
          activeCount={active?.length}
          archivedCount={archived?.length}
          label="Show questionnaires"
          idPrefix="questionnaires"
        />
      </div>
      <div
        id="questionnaires-panel"
        role="tabpanel"
        aria-labelledby={`questionnaires-tab-${lifecycle}`}
      >
        {/* Above the list, because these are the rows that cannot move
            until somebody acts on them. Shown on whichever tab they are
            actually in, so the panel never advertises records the list
            below it is not showing. */}
        <NeedsSetupPanel questionnaires={questionnaires ?? []} />
        {questionnaires?.length === 0 && showingArchived && (
          <EmptyState
            title="No archived questionnaires"
            description="Questionnaires you archive appear here, with their answers, approvals and history intact."
          />
        )}
        {questionnaires?.length === 0 && !showingArchived && (
          <EmptyState
            title="No active questionnaires"
            description={
              "Create or import a questionnaire to get started — internally, or on behalf of a customer asking before they sign."
            }
          />
        )}
        <div className="flex flex-col gap-3">
          {questionnaires?.map((questionnaire) => (
            <Card
              key={questionnaire.id}
              className="relative transition-colors hover:border-[var(--border-strong)]"
            >
              <CardContent className="flex items-center justify-between gap-3 pt-6">
                {/* The whole row opens the questionnaire; the menu sits
                  above it so its own clicks do not navigate. */}
                <Link
                  href={`/compliance/questionnaires/${questionnaire.id}`}
                  className={`${CARD_LINK_FOCUS} min-w-0 flex-1 after:absolute after:inset-0`}
                >
                  <div className="font-medium text-[var(--fg-default)]">
                    {questionnaire.title}
                  </div>
                  <div className="text-xs text-[var(--fg-subtle)]">
                    {questionnaire.source.replace(/_/g, " ")}
                    {questionnaire.progress
                      ? ` · ${questionnaire.progress.total} question${questionnaire.progress.total === 1 ? "" : "s"}`
                      : ""}
                    {/* Only in the archive. An active row saying nothing
                      about its lifecycle is saying the right thing. */}
                    {archivedOn(questionnaire.archived_at) && (
                      <> · Archived {archivedOn(questionnaire.archived_at)}</>
                    )}
                  </div>
                </Link>
                {/* Lifecycle first, then workflow status, then the
                    menu — one group, so nothing floats alone in the gap. */}
                <div className="relative z-10 flex shrink-0 items-center gap-2">
                  {questionnaire.archived_at && <ArchivedBadge />}
                  <StatusBadge status={questionnaire.status} />
                  <LifecycleMenu
                    kind="questionnaire"
                    id={questionnaire.id}
                    title={questionnaire.title}
                    canDelete={questionnaire.can_delete}
                    deleteBlockedReason={questionnaire.delete_blocked_reason}
                    archived={Boolean(questionnaire.archived_at)}
                    openHref={`/compliance/questionnaires/${questionnaire.id}`}
                  />
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </div>
  );
}

export function AuditsSection() {
  const [lifecycle, setLifecycle] = useState<"active" | "archived">("active");

  // Its own filter, like the sections beside it.
  const { data: active } = useQuery<Audit[]>({
    queryKey: ["compliance", "audits", { archived: false }],
    queryFn: () => apiFetch<Audit[]>("/api/v1/compliance/audits?archived=false"),
  });
  const { data: archived } = useQuery<Audit[]>({
    queryKey: ["compliance", "audits", { archived: true }],
    queryFn: () => apiFetch<Audit[]>("/api/v1/compliance/audits?archived=true"),
  });
  const showingArchived = lifecycle === "archived";
  const audits = showingArchived ? archived : active;

  return (
    <div className="mb-10">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
          Audits
        </h2>
        <CreatePanel label="Create audit">
          <CreateAuditForm />
        </CreatePanel>
      </div>

      <div className="mb-4">
        <LifecycleTabs
          value={lifecycle}
          onChange={setLifecycle}
          activeCount={active?.length}
          archivedCount={archived?.length}
          label="Show audits"
          idPrefix="audits"
        />
      </div>
      <div
        id="audits-panel"
        role="tabpanel"
        aria-labelledby={`audits-tab-${lifecycle}`}
      >
        {audits?.length === 0 && showingArchived && (
          <EmptyState
            title="No archived audits"
            description="Audits you archive appear here, with their findings, remediation and history intact."
          />
        )}
        {audits?.length === 0 && !showingArchived && (
          <EmptyState
            title="No active audits"
            description={
              "Record an audit to track findings and their remediation against a named auditor and period."
            }
          />
        )}
        <div className="flex flex-col gap-3">
          {audits?.map((audit) => (
            <Card
              key={audit.id}
              className="relative transition-colors hover:border-[var(--border-strong)]"
            >
              <CardContent className="flex items-center justify-between gap-3 pt-6">
                <Link
                  href={`/compliance/audits/${audit.id}`}
                  className={`${CARD_LINK_FOCUS} min-w-0 flex-1 after:absolute after:inset-0`}
                >
                  <div className="font-medium text-[var(--fg-default)]">
                    {audit.title}
                  </div>
                  <div className="text-xs text-[var(--fg-subtle)]">
                    {[
                      audit.framework_name,
                      audit.auditor_name
                        ? `Auditor: ${audit.auditor_name}`
                        : "No auditor set",
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                    {/* Review progress — scoped requirements the auditor
                        has dispositioned. Not compliance readiness, which
                        is a different number about a different thing. */}
                    {audit.progress.scoped > 0 && (
                      <>
                        {" · "}
                        {audit.progress.reviewed} / {audit.progress.scoped} reviewed
                      </>
                    )}
                    {audit.progress.open_findings > 0 && (
                      <>
                        {" · "}
                        {audit.progress.open_findings} open finding
                        {audit.progress.open_findings === 1 ? "" : "s"}
                      </>
                    )}
                    {audit.progress.ready_for_verification > 0 && (
                      <>
                        {" · "}
                        {audit.progress.ready_for_verification} awaiting verification
                      </>
                    )}
                    {archivedOn(audit.archived_at) && (
                      <> · Archived {archivedOn(audit.archived_at)}</>
                    )}
                  </div>
                </Link>
                <div className="relative z-10 flex shrink-0 items-center gap-2">
                  {audit.archived_at && <ArchivedBadge />}
                  <StatusBadge status={audit.status} />
                  <LifecycleMenu
                    kind="audit"
                    id={audit.id}
                    title={audit.title}
                    canDelete={audit.can_delete}
                    deleteBlockedReason={audit.delete_blocked_reason}
                    archived={Boolean(audit.archived_at)}
                    openHref={`/compliance/audits/${audit.id}`}
                  />
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </div>
  );
}

/** The security reviews customers put you through before they sign.
 *
 * Named "Enterprise Sales Security Reviews" until now, after a sales
 * module this product no longer has. The reviews themselves are real
 * compliance work and keep their data and their detail pages.
 *
 * The "Start review" form is gone. It required picking a sales
 * opportunity, and nothing in the product creates one any more — the
 * dropdown was permanently empty and the button permanently disabled,
 * which is dead UI dressed as a feature. Reviews already in the system
 * still open and still work; starting a new one needs a customer record
 * this product does not yet own, and saying so is better than offering
 * a control that cannot succeed.
 */
export function SecurityReviewsSection() {
  const [lifecycle, setLifecycle] = useState<"active" | "archived">("active");

  // Its own filter, like the sections above it.
  const { data: active } = useQuery<SecurityReview[]>({
    queryKey: ["compliance", "security-reviews", { archived: false }],
    queryFn: () =>
      apiFetch<SecurityReview[]>(
        "/api/v1/compliance/security-reviews?archived=false",
      ),
  });
  const { data: archived } = useQuery<SecurityReview[]>({
    queryKey: ["compliance", "security-reviews", { archived: true }],
    queryFn: () =>
      apiFetch<SecurityReview[]>(
        "/api/v1/compliance/security-reviews?archived=true",
      ),
  });
  const showingArchived = lifecycle === "archived";
  const reviews = showingArchived ? archived : active;

  return (
    <div className="mb-10">
      <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
        Customer security reviews
      </h2>

      <div className="mb-4">
        <LifecycleTabs
          value={lifecycle}
          onChange={setLifecycle}
          activeCount={active?.length}
          archivedCount={archived?.length}
          label="Show customer security reviews"
          idPrefix="security-reviews"
        />
      </div>

      <div
        id="security-reviews-panel"
        role="tabpanel"
        aria-labelledby={`security-reviews-tab-${lifecycle}`}
      >
        {reviews?.length === 0 && showingArchived && (
          <EmptyState
            title="No archived customer security reviews"
            description="Reviews you archive appear here, with their questionnaires and answers intact."
          />
        )}
        {reviews?.length === 0 && !showingArchived && (
          <EmptyState
            /* "No customer security reviews" while the Archived tab holds
               one is simply untrue. The empty state describes the view
               that is open, not the whole section. */
            title="No active customer security reviews"
            description={
              (archived?.length ?? 0) > 0
                ? "Reviews you have finished and archived are under Archived."
                : "Create a questionnaire marked customer-provided and name the customer — Veyntra opens the review for you and keeps the questionnaires in it together."
            }
          />
        )}

        <div className="flex flex-col gap-3">
          {reviews?.map((review) => (
            <Card
              key={review.id}
              className="relative transition-colors hover:border-[var(--border-strong)]"
            >
              <CardContent className="flex items-center justify-between gap-4 pt-6">
                <Link
                  href={`/compliance/security-reviews/${review.id}`}
                  className={`${CARD_LINK_FOCUS} min-w-0 flex-1 after:absolute after:inset-0`}
                >
                  <div className="font-medium text-[var(--fg-default)]">
                    {review.title ?? "Customer security review"}
                  </div>
                  {/* The work in the engagement, added up across every
                      questionnaire in it — the server's numbers, so this
                      card and the review page cannot disagree. */}
                  <div className="text-xs text-[var(--fg-subtle)]">
                    {review.customer_name ?? "No customer named"}
                    {" · "}
                    {review.progress.questionnaires} questionnaire
                    {review.progress.questionnaires === 1 ? "" : "s"}
                    {review.progress.total > 0 && (
                      <>
                        {" · "}
                        {review.progress.total} question
                        {review.progress.total === 1 ? "" : "s"}
                        {" · "}
                        {review.progress.approved}/{review.progress.total}{" "}
                        approved · {review.progress.percent_complete}%
                      </>
                    )}
                    {archivedOn(review.archived_at) && (
                      <> · Archived {archivedOn(review.archived_at)}</>
                    )}
                  </div>
                  {review.progress.needs_review > 0 && (
                    <div className="text-xs text-[var(--warning-700)]">
                      {review.progress.needs_review === 1
                        ? "1 answer needs a decision"
                        : `${review.progress.needs_review} answers need a decision`}
                    </div>
                  )}
                </Link>
                <div className="relative z-10 flex shrink-0 items-center gap-2">
                  {review.archived_at && <ArchivedBadge />}
                  <StatusBadge status={review.status} />
                  {/* Delete is never on offer. An engagement is the record
                      of a conversation with a customer; the most anybody
                      does with a finished one is put it away. */}
                  <LifecycleMenu
                    kind="security_review"
                    id={review.id}
                    title={review.title ?? "Customer security review"}
                    canDelete={false}
                    deleteBlockedReason="A customer security review is kept as history."
                    archived={review.archived_at !== null}
                    openHref={`/compliance/security-reviews/${review.id}`}
                  />
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </div>
  );
}
