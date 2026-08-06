"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { OnboardingStepper } from "@/components/auth/onboarding-stepper";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { apiFetch } from "@/lib/api";
import { isSafeRedirectTarget } from "@/lib/auth-redirect";
import {
  ONBOARDING_GOALS,
  type Framework,
  type OnboardingProfile,
  type Readiness,
} from "@/lib/types";

// spec §68's 10 named steps, condensed to 9 real screens here: step 1
// ("Company") and step 2 ("Business profile") are collected together on
// one screen since spec gives step 1 no fields of its own beyond the
// organization identity already captured at signup — see
// docs/DECISIONS.md for the full reasoning.
const SCREEN_LABELS = [
  "Company",
  "Goals",
  "Compliance profile",
  "Security profile",
  "Sales profile",
  "Support profile",
  "Connect tools",
  "Upload knowledge",
  "AI analysis",
];

const EMPLOYEE_RANGES = ["1-10", "11-50", "51-200", "201-1000", "1000+"];

const ONBOARDING_STEPS = SCREEN_LABELS.map((label) => ({ label }));

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
    <Card>
      <CardContent className="flex flex-col gap-4 pt-6">
        <p className="text-sm text-[var(--fg-muted)]">
          Tell us about your company.
        </p>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="industry">Industry</Label>
          <Input id="industry" value={industry} onChange={(e) => setIndustry(e.target.value)} />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label>Employee count</Label>
          <select
            className="flex h-9 rounded-md border border-[var(--border-strong)] bg-[var(--bg-surface)] px-3 py-1 text-sm shadow-sm"
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
          disabled={!industry.trim() || submit.isPending}
          onClick={() => submit.mutate()}
        >
          Continue
        </Button>
      </CardContent>
    </Card>
  );
}

function GoalsStep({ onDone }: { onDone: () => void }) {
  const [selected, setSelected] = useState<string[]>([]);

  const submit = useMutation({
    mutationFn: () =>
      apiFetch<OnboardingProfile>("/api/v1/onboarding/goals", {
        method: "PUT",
        body: { selected_goals: selected },
      }),
    onSuccess: onDone,
  });

  function toggle(key: string) {
    setSelected((prev) => (prev.includes(key) ? prev.filter((g) => g !== key) : [...prev, key]));
  }

  return (
    <Card>
      <CardContent className="flex flex-col gap-4 pt-6">
        <p className="text-sm text-[var(--fg-muted)]">
          What do you want to improve? Choose any that apply.
        </p>
        <div className="flex flex-col gap-2">
          {ONBOARDING_GOALS.map((goal) => (
            <label key={goal.key} className="flex items-center gap-2 text-sm text-[var(--fg-muted)]">
              <input
                type="checkbox"
                checked={selected.includes(goal.key)}
                onChange={() => toggle(goal.key)}
              />
              {goal.label}
            </label>
          ))}
        </div>
        <Button
          className="self-start"
          disabled={selected.length === 0 || submit.isPending}
          onClick={() => submit.mutate()}
        >
          Continue
        </Button>
      </CardContent>
    </Card>
  );
}

function ComplianceProfileStep({ onDone }: { onDone: () => void }) {
  const [selected, setSelected] = useState<string[]>([]);
  const { data: frameworks } = useQuery<Framework[]>({
    queryKey: ["compliance", "frameworks"],
    queryFn: () => apiFetch<Framework[]>("/api/v1/compliance/frameworks"),
  });

  const submit = useMutation({
    mutationFn: () =>
      apiFetch<OnboardingProfile>("/api/v1/onboarding/compliance-profile", {
        method: "PUT",
        body: { selected_framework_keys: selected },
      }),
    onSuccess: onDone,
  });

  function toggle(key: string) {
    setSelected((prev) => (prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]));
  }

  return (
    <Card>
      <CardContent className="flex flex-col gap-4 pt-6">
        <p className="text-sm text-[var(--fg-muted)]">
          Which compliance frameworks matter to you?
        </p>
        <div className="flex flex-col gap-2">
          {frameworks?.map((framework) => (
            <label key={framework.key} className="flex items-center gap-2 text-sm text-[var(--fg-muted)]">
              <input
                type="checkbox"
                checked={selected.includes(framework.key)}
                onChange={() => toggle(framework.key)}
              />
              {framework.name}
            </label>
          ))}
          {frameworks?.length === 0 && (
            <p className="text-sm text-[var(--fg-subtle)]">No frameworks in the catalog yet.</p>
          )}
        </div>
        <div className="flex gap-2">
          <Button disabled={submit.isPending} onClick={() => submit.mutate()}>
            Continue
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function SecurityProfileStep({ onDone }: { onDone: () => void }) {
  const [provider, setProvider] = useState("none");

  const submit = useMutation({
    mutationFn: () =>
      apiFetch<OnboardingProfile>("/api/v1/onboarding/security-profile", {
        method: "PUT",
        body: { primary_cloud_provider: provider },
      }),
    onSuccess: onDone,
  });

  return (
    <Card>
      <CardContent className="flex flex-col gap-4 pt-6">
        <p className="text-sm text-[var(--fg-muted)]">
          What&apos;s your primary cloud provider?
        </p>
        <select
          className="flex h-9 w-48 rounded-md border border-[var(--border-strong)] bg-[var(--bg-surface)] px-3 py-1 text-sm shadow-sm"
          value={provider}
          onChange={(e) => setProvider(e.target.value)}
        >
          <option value="none">None / Not sure</option>
          <option value="aws">AWS</option>
          <option value="azure">Azure</option>
          <option value="gcp">GCP</option>
        </select>
        <Button className="self-start" disabled={submit.isPending} onClick={() => submit.mutate()}>
          Continue
        </Button>
      </CardContent>
    </Card>
  );
}

function SalesProfileStep({ onDone }: { onDone: () => void }) {
  const [focus, setFocus] = useState("");

  const submit = useMutation({
    mutationFn: () =>
      apiFetch<OnboardingProfile>("/api/v1/onboarding/sales-profile", {
        method: "PUT",
        body: { sales_focus: focus },
      }),
    onSuccess: onDone,
  });

  return (
    <Card>
      <CardContent className="flex flex-col gap-4 pt-6">
        <p className="text-sm text-[var(--fg-muted)]">What&apos;s your sales focus?</p>
        <Input
          placeholder="e.g. Enterprise SaaS accounts in Europe"
          value={focus}
          onChange={(e) => setFocus(e.target.value)}
        />
        <Button
          className="self-start"
          disabled={!focus.trim() || submit.isPending}
          onClick={() => submit.mutate()}
        >
          Continue
        </Button>
      </CardContent>
    </Card>
  );
}

const SUPPORT_CHANNEL_OPTIONS = ["email", "chat", "phone"];

function SupportProfileStep({ onDone }: { onDone: () => void }) {
  const [selected, setSelected] = useState<string[]>([]);

  const submit = useMutation({
    mutationFn: () =>
      apiFetch<OnboardingProfile>("/api/v1/onboarding/support-profile", {
        method: "PUT",
        body: { support_channels: selected },
      }),
    onSuccess: onDone,
  });

  function toggle(channel: string) {
    setSelected((prev) =>
      prev.includes(channel) ? prev.filter((c) => c !== channel) : [...prev, channel],
    );
  }

  return (
    <Card>
      <CardContent className="flex flex-col gap-4 pt-6">
        <p className="text-sm text-[var(--fg-muted)]">
          Which support channels do you use?
        </p>
        <div className="flex flex-col gap-2">
          {SUPPORT_CHANNEL_OPTIONS.map((channel) => (
            <label key={channel} className="flex items-center gap-2 text-sm capitalize text-[var(--fg-muted)]">
              <input
                type="checkbox"
                checked={selected.includes(channel)}
                onChange={() => toggle(channel)}
              />
              {channel}
            </label>
          ))}
        </div>
        <Button disabled={submit.isPending} onClick={() => submit.mutate()}>
          Continue
        </Button>
      </CardContent>
    </Card>
  );
}

function PassThroughStep({
  title,
  description,
  linkHref,
  linkLabel,
  onDone,
}: {
  title: string;
  description: string;
  linkHref: string;
  linkLabel: string;
  onDone: () => void;
}) {
  const advance = useMutation({
    mutationFn: () => apiFetch<OnboardingProfile>("/api/v1/onboarding/advance", { method: "POST" }),
    onSuccess: onDone,
  });

  return (
    <Card>
      <CardContent className="flex flex-col gap-4 pt-6">
        <div>
          <h3 className="font-medium text-[var(--fg-default)]">{title}</h3>
          <p className="text-sm text-[var(--fg-muted)]">{description}</p>
        </div>
        <Link href={linkHref} target="_blank" className="self-start">
          <Button variant="outline">{linkLabel}</Button>
        </Link>
        <Button className="self-start" disabled={advance.isPending} onClick={() => advance.mutate()}>
          Configure later
        </Button>
      </CardContent>
    </Card>
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
    mutationFn: () => apiFetch<OnboardingProfile>("/api/v1/onboarding/complete", { method: "POST" }),
    onSuccess: () => {
      // Honors a redirect carried through from signup (a visitor who hit
      // a protected route while unauthenticated, then created a new
      // account instead of logging in) — falls back to the dashboard for
      // the overwhelmingly common case of no pending redirect.
      const requestedRedirect = searchParams.get("redirect");
      router.push(isSafeRedirectTarget(requestedRedirect) ? requestedRedirect : "/dashboard");
    },
  });

  const dimensions = readiness
    ? [
        readiness.compliance,
        readiness.security,
        readiness.sales_automation,
        readiness.support_automation,
        readiness.process_automation,
      ]
    : [];

  return (
    <Card>
      <CardContent className="flex flex-col gap-4 pt-6">
        <h3 className="font-medium text-[var(--fg-default)]">Your Business AI Readiness</h3>
        {isLoading && <p className="text-sm text-[var(--fg-muted)]">Computing…</p>}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
          {dimensions.map((dimension) => (
            <div key={dimension.label} className="rounded border border-[var(--border-default)] p-3 text-center">
              <div className="text-2xl font-semibold text-[var(--fg-default)]">{dimension.percent}%</div>
              <div className="text-xs text-[var(--fg-muted)]">{dimension.label}</div>
            </div>
          ))}
        </div>
        {readiness && readiness.opportunities.length > 0 && (
          <div>
            <h4 className="mb-2 text-sm font-medium text-[var(--fg-default)]">Top opportunities</h4>
            <ul className="flex flex-col gap-1.5">
              {readiness.opportunities.map((opportunity) => (
                <li key={opportunity.title} className="text-sm text-[var(--fg-muted)]">
                  <span className="font-medium">{opportunity.title}</span> — {opportunity.detail}
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
          Open Business Command Center
        </Button>
      </CardContent>
    </Card>
  );
}

export default function OnboardingPage() {
  const queryClient = useQueryClient();
  const [screen, setScreen] = useState<number | null>(null);

  const { data: status, isLoading } = useQuery<OnboardingProfile>({
    queryKey: ["onboarding", "status"],
    queryFn: () => apiFetch<OnboardingProfile>("/api/v1/onboarding/status"),
  });

  // `screen` overrides the resumed step once the user starts navigating
  // within this session; before that, the resume point is derived
  // directly from the fetched status at render time rather than synced
  // via an effect.
  const resumedScreen = status ? Math.min(status.current_step - 1, SCREEN_LABELS.length - 1) : null;
  const effectiveScreen = screen ?? resumedScreen;

  function advanceScreen() {
    queryClient.invalidateQueries({ queryKey: ["onboarding", "status"] });
    setScreen(Math.min((effectiveScreen ?? 0) + 1, SCREEN_LABELS.length - 1));
  }

  if (effectiveScreen === null) {
    return (
      <div className="mx-auto max-w-2xl">
        <PageHeader title="Onboarding" description="A guided setup for your organization." />
        <p className="text-sm text-[var(--fg-muted)]">{isLoading ? "Loading…" : ""}</p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader title="Onboarding" description="A guided setup for your organization — skip anything you'd rather configure later." />
      <div className="mb-8">
        <OnboardingStepper steps={ONBOARDING_STEPS} currentIndex={effectiveScreen} />
      </div>
      {effectiveScreen === 0 && <CompanyStep onDone={advanceScreen} />}
      {effectiveScreen === 1 && <GoalsStep onDone={advanceScreen} />}
      {effectiveScreen === 2 && <ComplianceProfileStep onDone={advanceScreen} />}
      {effectiveScreen === 3 && <SecurityProfileStep onDone={advanceScreen} />}
      {effectiveScreen === 4 && <SalesProfileStep onDone={advanceScreen} />}
      {effectiveScreen === 5 && <SupportProfileStep onDone={advanceScreen} />}
      {effectiveScreen === 6 && (
        <PassThroughStep
          title="Connect tools"
          description="Connect a real integration now, or configure it later from Settings."
          linkHref="/settings/integrations"
          linkLabel="Open Integrations"
          onDone={advanceScreen}
        />
      )}
      {effectiveScreen === 7 && (
        <PassThroughStep
          title="Upload knowledge"
          description="Upload a document now, or add it later from Knowledge."
          linkHref="/knowledge"
          linkLabel="Open Knowledge"
          onDone={advanceScreen}
        />
      )}
      {effectiveScreen === 8 && <ReadinessStep />}
    </div>
  );
}
