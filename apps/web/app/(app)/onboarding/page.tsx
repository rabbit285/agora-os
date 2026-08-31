"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useMutation, useQuery } from "@tanstack/react-query";

import { OnboardingStepper } from "@/components/auth/onboarding-stepper";
import { DocumentLibrary } from "@/components/compliance/document-library";
import { FrameworkApplicability } from "@/components/compliance/framework-applicability";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { apiFetch } from "@/lib/api";
import { isSafeRedirectTarget } from "@/lib/auth-redirect";
import type { AISystem, OnboardingProfile, Readiness } from "@/lib/types";

/** AI-first onboarding.
 *
 * The old flow asked for a sales focus and a list of support channels
 * before it asked anything that decided a compliance obligation. This one
 * collects only what changes the answer — what the company is, what AI it
 * runs, and its documents — and each step leaves the product measurably
 * more useful than the one before.
 *
 * Every step reuses the component that owns that job elsewhere in the
 * product rather than a simplified copy. A customer who fills something
 * in during onboarding and finds a different screen for it afterwards has
 * been taught the wrong thing twice.
 */

const SCREEN_LABELS = [
  "Company",
  "What applies",
  "AI systems",
  "Documents",
  "Readiness",
];

const EMPLOYEE_RANGES = ["1-10", "11-50", "51-200", "201-1000", "1000+"];

const ONBOARDING_STEPS = SCREEN_LABELS.map((label) => ({ label }));

function StepShell({
  title,
  description,
  children,
  onSkip,
  skipLabel = "Skip for now",
}: {
  title: string;
  description: string;
  children: React.ReactNode;
  onSkip?: () => void;
  skipLabel?: string;
}) {
  return (
    <div>
      <h2 className="text-lg font-semibold text-[var(--fg-default)]">{title}</h2>
      <p className="mb-4 mt-1 text-sm leading-relaxed text-[var(--fg-muted)]">{description}</p>
      {children}
      {onSkip && (
        <Button variant="outline" size="sm" className="mt-4" onClick={onSkip}>
          {skipLabel}
        </Button>
      )}
    </div>
  );
}

function CompanyStep({ onDone }: { onDone: () => void }) {
  const [industry, setIndustry] = useState("");
  const [employeeCountRange, setEmployeeCountRange] = useState(EMPLOYEE_RANGES[0]);

  const submit = useMutation({
    mutationFn: () =>
      apiFetch<OnboardingProfile>("/api/v1/onboarding/company", {
        method: "PUT",
        body: { industry, employee_count_range: employeeCountRange },
      }),
    onSuccess: onDone,
  });

  return (
    <StepShell
      title="Tell us about your company"
      description="Two questions that shape everything after this."
    >
      <Card>
        <CardContent className="flex flex-col gap-4 pt-6">
          <div>
            <Label htmlFor="industry">Industry</Label>
            <Input
              id="industry"
              value={industry}
              onChange={(e) => setIndustry(e.target.value)}
              placeholder="B2B SaaS / AI software"
            />
          </div>
          <div>
            <Label htmlFor="employees">Employee count</Label>
            <select
              id="employees"
              className="flex h-9 w-full rounded-md border border-[var(--border-strong)] bg-[var(--bg-surface)] px-3 py-1 text-sm text-[var(--fg-default)]"
              value={employeeCountRange}
              onChange={(e) => setEmployeeCountRange(e.target.value)}
            >
              {EMPLOYEE_RANGES.map((range) => (
                <option key={range} value={range}>
                  {range}
                </option>
              ))}
            </select>
          </div>
          <Button
            className="self-start"
            disabled={submit.isPending}
            onClick={() => submit.mutate()}
          >
            Continue
          </Button>
        </CardContent>
      </Card>
    </StepShell>
  );
}

/** Adding an AI system during onboarding.
 *
 * Deliberately asks for the minimum that makes an inventory entry worth
 * having — a name and a purpose. The governance detail that decides its
 * obligations is asked for on the AI Systems screen, where the record can
 * be filled in over time by the people who actually know the answers.
 */
function AISystemsStep({ onDone }: { onDone: () => void }) {
  const [name, setName] = useState("");
  const [purpose, setPurpose] = useState("");

  const { data: systems, refetch } = useQuery<AISystem[]>({
    queryKey: ["compliance", "ai-systems"],
    queryFn: () => apiFetch<AISystem[]>("/api/v1/compliance/ai-systems"),
  });

  const add = useMutation({
    mutationFn: () =>
      apiFetch("/api/v1/compliance/ai-systems", {
        method: "POST",
        body: { name, purpose },
      }),
    onSuccess: () => {
      setName("");
      setPurpose("");
      void refetch();
    },
  });

  return (
    <StepShell
      title="What AI do you run?"
      description="Anything that uses a model — a support agent, an internal copilot, a feature in your own product. Third-party tools count: using ChatGPT or Copilot makes you a deployer under the EU AI Act."
      onSkip={onDone}
      skipLabel={systems?.length ? "Continue" : "We don't use AI yet"}
    >
      <Card className="mb-3">
        <CardContent className="flex flex-col gap-3 pt-6">
          <Input
            placeholder="Name, e.g. Customer Support AI"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <Input
            placeholder="What it does, e.g. drafts replies from our knowledge base"
            value={purpose}
            onChange={(e) => setPurpose(e.target.value)}
          />
          <Button
            className="self-start"
            size="sm"
            disabled={!name.trim() || !purpose.trim() || add.isPending}
            onClick={() => add.mutate()}
          >
            Add AI system
          </Button>
        </CardContent>
      </Card>

      {(systems ?? []).length > 0 && (
        <div className="flex flex-col gap-2">
          {(systems ?? []).map((system) => (
            <Card key={system.id}>
              <CardContent className="py-3">
                <div className="font-medium text-[var(--fg-default)]">{system.name}</div>
                <div className="text-xs text-[var(--fg-subtle)]">{system.purpose}</div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </StepShell>
  );
}

function ReadinessStep() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { data: readiness, isLoading } = useQuery<Readiness>({
    queryKey: ["onboarding", "readiness"],
    queryFn: () => apiFetch<Readiness>("/api/v1/onboarding/readiness"),
  });

  const complete = useMutation({
    mutationFn: () =>
      apiFetch<OnboardingProfile>("/api/v1/onboarding/complete", { method: "POST" }),
    onSuccess: () => {
      const requestedRedirect = searchParams.get("redirect");
      router.push(isSafeRedirectTarget(requestedRedirect) ? requestedRedirect : "/dashboard");
    },
  });

  const dimensions = readiness
    ? [
        readiness.framework_adoption,
        readiness.compliance,
        readiness.evidence_coverage,
        readiness.security,
      ]
    : [];

  return (
    <StepShell
      title="Where you stand"
      description="Computed from what is actually recorded, not a score we assigned you."
    >
      <Card>
        <CardContent className="flex flex-col gap-4 pt-6">
          {isLoading && <p className="text-sm text-[var(--fg-muted)]">Computing…</p>}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {dimensions.map((dimension) => (
              <div
                key={dimension.label}
                className="rounded border border-[var(--border-default)] p-3 text-center"
              >
                <div className="text-2xl font-semibold text-[var(--fg-default)]">
                  {dimension.percent}%
                </div>
                <div className="text-xs text-[var(--fg-muted)]">{dimension.label}</div>
              </div>
            ))}
          </div>

          {readiness && readiness.opportunities.length > 0 && (
            <div>
              <h3 className="mb-2 text-sm font-medium text-[var(--fg-default)]">
                What to do next
              </h3>
              <ul className="flex flex-col gap-1.5">
                {readiness.opportunities.map((opportunity) => (
                  <li key={opportunity.title} className="text-sm text-[var(--fg-muted)]">
                    <span className="font-medium">{opportunity.title}</span> —{" "}
                    {opportunity.detail}
                  </li>
                ))}
              </ul>
            </div>
          )}

          <Button
            className="self-start"
            disabled={complete.isPending}
            onClick={() => complete.mutate()}
          >
            Go to my dashboard
          </Button>
        </CardContent>
      </Card>
    </StepShell>
  );
}

export default function OnboardingPage() {
  const [screen, setScreen] = useState<number | null>(null);

  const { data: status, isLoading } = useQuery<OnboardingProfile>({
    queryKey: ["onboarding", "status"],
    queryFn: () => apiFetch<OnboardingProfile>("/api/v1/onboarding/status"),
  });

  const resumedScreen = status
    ? Math.min(status.current_step - 1, SCREEN_LABELS.length - 1)
    : null;
  const effectiveScreen = screen ?? resumedScreen;

  function advanceScreen() {
    setScreen(Math.min((effectiveScreen ?? 0) + 1, SCREEN_LABELS.length - 1));
  }

  if (effectiveScreen === null) {
    return (
      <div className="mx-auto max-w-3xl">
        <PageHeader title="Set up Veyntra" description="A few questions, then we get to work." />
        <p className="text-sm text-[var(--fg-muted)]">{isLoading ? "Loading…" : ""}</p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader
        title="Set up Veyntra"
        description="A few questions, then we get to work. Skip anything you would rather come back to."
      />
      <div className="mb-8">
        <OnboardingStepper steps={ONBOARDING_STEPS} currentIndex={effectiveScreen} />
      </div>

      {effectiveScreen === 0 && <CompanyStep onDone={advanceScreen} />}

      {effectiveScreen === 1 && (
        <StepShell
          title="What applies to you"
          description="Answer these and Veyntra works out which frameworks you are held to, and explains why. Adopting one builds its control set, which is what your documents map to."
          onSkip={advanceScreen}
          skipLabel="Continue"
        >
          {/* The same component the Compliance screen uses. A customer who
              answers these here and meets a different form later has been
              taught the wrong thing twice. */}
          <FrameworkApplicability />
        </StepShell>
      )}

      {effectiveScreen === 2 && <AISystemsStep onDone={advanceScreen} />}

      {effectiveScreen === 3 && (
        <StepShell
          title="Upload your documents"
          description="Privacy notice, security policy, DPA, AI policy — whatever you already have. Veyntra reads each one and proposes which controls it evidences. You do not need to map anything by hand."
          onSkip={advanceScreen}
          skipLabel="Continue"
        >
          <DocumentLibrary />
          <p className="mt-2 text-xs text-[var(--fg-subtle)]">
            Processing continues in the background — you can move on without waiting, and
            review the proposals from{" "}
            <Link href="/documents" className="underline">
              Documents
            </Link>{" "}
            at any time.
          </p>
        </StepShell>
      )}

      {effectiveScreen === 4 && <ReadinessStep />}
    </div>
  );
}
