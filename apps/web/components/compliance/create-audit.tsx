"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, apiFetch } from "@/lib/api";
import type { Audit, Framework, OrganizationPerson } from "@/lib/types";

/** Opening an audit, framework first.
 *
 * The framework is what makes an audit preparable: it decides which
 * requirements Veyntra walks, which controls answer them, what evidence
 * is on file and which gaps are already known. So it is the choice the
 * form is built around, and "Custom / No framework" sits at the bottom
 * as the deliberate alternative it is.
 *
 * It used to be the default, which made the exceptional path look like
 * the normal one — and a person who never touched the dropdown got an
 * audit that prepared nothing, then had to work out why.
 *
 * Two workflows, and the form says which one you are in: a framework
 * audit that Veyntra prepares, and a custom audit somebody scopes
 * themselves. The button, the helper text and the validation all change
 * together, so the difference is never something to infer.
 */
const SELECT_CLASS =
  "flex h-9 w-full rounded-md border border-[var(--border-strong)] bg-[var(--bg-default)] px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--border-focus)]";

// The value that means "somebody chose custom", as opposed to the empty
// string that means "somebody has not chosen yet". Two different states
// that both used to be "".
const CUSTOM = "custom";

// Enough to be a description rather than a placeholder. The server
// applies the same floor; this is so the button explains itself before
// somebody presses it.
const MIN_SCOPE = 20;

function Field({
  label,
  htmlFor,
  hint,
  children,
}: {
  label: string;
  htmlFor: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      {/* A permanent label. A placeholder disappears the moment somebody
          types, which is exactly when they most want to check what they
          are filling in. */}
      <label
        htmlFor={htmlFor}
        className="mb-1 block text-xs font-medium text-[var(--fg-muted)]"
      >
        {label}
      </label>
      {children}
      {hint && (
        <p className="mt-1 text-xs text-[var(--fg-subtle)]">{hint}</p>
      )}
    </div>
  );
}

export function CreateAuditForm({ onCreated }: { onCreated?: () => void }) {
  const queryClient = useQueryClient();

  const [title, setTitle] = useState("");
  const [titleTouched, setTitleTouched] = useState(false);
  const [frameworkChoice, setFrameworkChoice] = useState("");
  const [auditorId, setAuditorId] = useState("");
  // Which kind of auditor this is, chosen rather than inferred from an
  // empty box. The old form had one dropdown whose blank option meant
  // "external", so an audit conducted by a colleague nobody had picked
  // yet was indistinguishable from one conducted by an outside firm —
  // and the report went on to print "(external)" against their name.
  const [external, setExternal] = useState(false);
  const [externalAuditor, setExternalAuditor] = useState("");
  const [externalOrganization, setExternalOrganization] = useState("");
  const [scope, setScope] = useState("");
  const [scopeTouched, setScopeTouched] = useState(false);
  const [scopeConflict, setScopeConflict] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const { data: frameworks } = useQuery<Framework[]>({
    queryKey: ["compliance", "frameworks"],
    queryFn: () => apiFetch<Framework[]>("/api/v1/compliance/frameworks"),
  });
  const { data: people } = useQuery<OrganizationPerson[]>({
    queryKey: ["organization", "people"],
    queryFn: () =>
      apiFetch<OrganizationPerson[]>("/api/v1/organizations/current/people"),
  });

  const isCustom = frameworkChoice === CUSTOM;
  const chosen = Boolean(frameworkChoice);

  /** Fill the empty boxes from the framework, and only the empty ones. */
  const chooseFramework = (next: string) => {
    setFrameworkChoice(next);
    setScopeConflict(null);
    if (next === CUSTOM || next === "") {
      // Custom scopes itself, and nothing suggests a title for it.
      if (!scopeTouched) setScope("");
      return;
    }
    const picked = (frameworks ?? []).find((entry) => entry.id === next);
    if (!picked) return;

    if (!titleTouched && !title.trim()) {
      setTitle(`${picked.name} Internal Audit`);
    }
    if (!scopeTouched) {
      setScope(picked.suggested_audit_scope ?? "");
    } else if (
      picked.suggested_audit_scope &&
      scope.trim() &&
      scope.trim() !== picked.suggested_audit_scope
    ) {
      // Their words stay. Silently replacing a scope somebody wrote — the
      // one field only they can fill in — because they changed a dropdown
      // is not a thing to do quietly, so the offer is made instead.
      setScopeConflict(picked.suggested_audit_scope);
    }
  };

  const create = useMutation<Audit, unknown, void>({
    mutationFn: () =>
      apiFetch<Audit>("/api/v1/compliance/audits", {
        method: "POST",
        body: {
          title: title.trim(),
          framework_id: isCustom ? null : frameworkChoice || null,
          auditor_user_id: external ? null : auditorId || null,
          auditor_name: external
            ? externalAuditor.trim() || null
            : ((people ?? []).find((person) => person.id === auditorId)
                ?.full_name ?? null),
          // Recorded, so nothing downstream has to guess. The server
          // re-establishes "internal" from membership rather than
          // trusting this, but an external auditor is only external
          // because somebody said so here.
          auditor_type: external ? "external" : auditorId ? "internal" : null,
          auditor_organization: external
            ? externalOrganization.trim() || null
            : null,
          scope: scope.trim() || null,
        },
      }),
    onMutate: () => setError(null),
    onSuccess: async () => {
      setTitle("");
      setTitleTouched(false);
      setFrameworkChoice("");
      setAuditorId("");
      setExternal(false);
      setExternalAuditor("");
      setExternalOrganization("");
      setScope("");
      setScopeTouched(false);
      setScopeConflict(null);
      await queryClient.invalidateQueries({ queryKey: ["compliance", "audits"] });
      onCreated?.();
    },
    onError: (cause) =>
      setError(
        cause instanceof ApiError
          ? cause.message
          : "The audit could not be created. Nothing was changed.",
      ),
  });

  const auditorNamed = external
    ? Boolean(externalAuditor.trim())
    : Boolean(auditorId);
  const scopeLongEnough = scope.trim().length >= MIN_SCOPE;
  const ready =
    Boolean(title.trim()) && chosen && auditorNamed && scopeLongEnough;

  return (
    <div className="flex flex-col gap-3">
      <Field label="Audit title" htmlFor="audit-title">
        <Input
          id="audit-title"
          placeholder="ISO 42001 Internal Audit"
          value={title}
          onChange={(event) => {
            setTitleTouched(true);
            setTitle(event.target.value);
          }}
        />
      </Field>

      <Field label={isCustom ? "Audit type" : "Framework"} htmlFor="audit-framework">
        <select
          id="audit-framework"
          className={SELECT_CLASS}
          value={frameworkChoice}
          onChange={(event) => chooseFramework(event.target.value)}
        >
          {/* Nothing is chosen until somebody chooses. The old default was
              "Custom / No framework", which quietly opted everybody into
              the path that prepares nothing. */}
          <option value="">Select framework…</option>
          {(frameworks ?? []).map((entry) => (
            <option key={entry.id} value={entry.id}>
              {entry.name}
            </option>
          ))}
          <option value={CUSTOM}>Custom / No framework</option>
        </select>
      </Field>

      {/* Internal is the ordinary case and the default path. External
          is a deliberate switch, so "who conducted this" is a fact the
          form records rather than one the report later infers. */}
      {external ? (
        <>
          <Field
            label="External auditor"
            htmlFor="audit-external-auditor"
            hint="Recorded as an external auditor. They have no Veyntra account."
          >
            <Input
              id="audit-external-auditor"
              placeholder="Jane Smith"
              value={externalAuditor}
              onChange={(event) => setExternalAuditor(event.target.value)}
            />
          </Field>
          <Field
            label="External auditor organization"
            htmlFor="audit-external-organization"
            hint="Optional. The firm they audit on behalf of."
          >
            <Input
              id="audit-external-organization"
              placeholder="ABC Compliance Ltd."
              value={externalOrganization}
              onChange={(event) => setExternalOrganization(event.target.value)}
            />
          </Field>
          <button
            type="button"
            className="self-start text-xs text-[var(--fg-link)] underline"
            onClick={() => {
              setExternal(false);
              setExternalAuditor("");
              setExternalOrganization("");
            }}
          >
            Use an internal team member instead
          </button>
        </>
      ) : (
        <>
          <Field
            label="Auditor"
            htmlFor="audit-auditor"
            hint="An internal audit is conducted by somebody in your organization."
          >
            <select
              id="audit-auditor"
              className={SELECT_CLASS}
              value={auditorId}
              onChange={(event) => setAuditorId(event.target.value)}
            >
              <option value="">Select team member…</option>
              {(people ?? []).map((person) => (
                <option key={person.id} value={person.id}>
                  {person.full_name ?? person.email}
                </option>
              ))}
            </select>
          </Field>
          <button
            type="button"
            className="self-start text-xs text-[var(--fg-link)] underline"
            onClick={() => {
              setExternal(true);
              setAuditorId("");
            }}
          >
            Use external auditor
          </button>
        </>
      )}

      <Field
        label="Scope"
        htmlFor="audit-scope"
        hint={
          scope.trim() && !scopeLongEnough
            ? "Describe what this audit covers — a reader checks the report against it."
            : undefined
        }
      >
        <Textarea
          id="audit-scope"
          rows={3}
          placeholder="What this audit covers"
          value={scope}
          onChange={(event) => {
            setScopeTouched(true);
            setScope(event.target.value);
          }}
        />
      </Field>

      {scopeConflict && (
        <div className="rounded-md border border-[var(--border-default)] bg-[var(--bg-subtle)] px-3 py-2 text-xs">
          <p className="text-[var(--fg-muted)]">
            You have written your own scope. Replace it with the suggested
            wording for this framework?
          </p>
          <div className="mt-2 flex gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={() => {
                setScope(scopeConflict);
                setScopeConflict(null);
              }}
            >
              Use suggested scope
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setScopeConflict(null)}
            >
              Keep mine
            </Button>
          </div>
        </div>
      )}

      <p className="text-xs text-[var(--fg-subtle)]">
        {isCustom
          ? "Custom audits are scoped manually. Select a framework to let Veyntra prepare requirements, controls and evidence automatically."
          : chosen
            ? "Veyntra will prepare applicable requirements, controls, current evidence, known gaps and remediation for your review."
            : "Choose the framework this audit is against, or Custom for an engagement Veyntra cannot scope."}
      </p>

      <div>
        <Button disabled={!ready || create.isPending} onClick={() => create.mutate()}>
          {create.isPending
            ? "Preparing…"
            : isCustom
              ? "Create Custom Audit"
              : "Create & Prepare Audit"}
        </Button>
      </div>

      {error && (
        <p role="alert" className="text-sm text-[var(--fg-danger)]">
          {error}
        </p>
      )}
    </div>
  );
}
