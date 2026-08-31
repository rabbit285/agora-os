"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowRight } from "lucide-react";

import { CARD_LINK_FOCUS } from "@/lib/focus";
import { PageHeader } from "@/components/page-header";
import { Card, CardContent } from "@/components/ui/card";

/** The old stacked Compliance screen, now a signpost.
 *
 * This route used to render fifteen unrelated sections — framework
 * readiness, document upload, controls, the risk register, policies,
 * questionnaires, audits, a second AI system inventory, DPIAs, DSARs,
 * data transfers, vendors, the Trust Center and framework administration
 * — with the sidebar linking into it by anchor. Every one of those is now
 * a page that answers a single question.
 *
 * The anchors are kept working rather than dropped: `/compliance#privacy`
 * is in people's history and in the sidebar of any tab open since before
 * this change, and a bookmark that silently lands on the wrong screen is
 * worse than one that 404s.
 */
const ANCHOR_ROUTES: Record<string, string> = {
  "#frameworks": "/compliance/frameworks",
  "#controls": "/compliance/controls",
  // Policies had no anchor of its own — it was a section inside
  // #controls — so that anchor keeps its destination and Policies is
  // reachable from the signpost below and the sidebar.
  "#assessments": "/compliance/assessments",
  "#privacy": "/compliance/privacy",
  "#vendors": "/compliance/vendors",
  "#ai-governance": "/ai-systems",
};

const DESTINATIONS: { href: string; title: string; question: string }[] = [
  {
    href: "/compliance/frameworks",
    title: "Frameworks",
    question: "Which frameworks apply, and how ready are we?",
  },
  {
    href: "/compliance/controls",
    title: "Controls & Risk",
    question: "Which controls are working, and where are the gaps?",
  },
  {
    href: "/documents",
    title: "Documents",
    question: "What has Veyntra analyzed?",
  },
  {
    href: "/compliance/policies",
    title: "Policies",
    question: "Which policies do we have, who owns them, and are they current?",
  },
  {
    href: "/ai-systems",
    title: "AI Systems",
    question: "Which AI systems do we operate, and what obligations follow?",
  },
  {
    href: "/compliance/assessments",
    title: "Assessments",
    question: "What is being assessed, by us and by our customers?",
  },
  {
    href: "/compliance/privacy",
    title: "Privacy",
    question: "What privacy operations require attention?",
  },
  {
    href: "/compliance/vendors",
    title: "Vendors & Trust",
    question: "Which third parties create compliance risk?",
  },
];

export default function CompliancePage() {
  const router = useRouter();

  useEffect(() => {
    // The hash never reaches the server, so this has to run client-side.
    const target = ANCHOR_ROUTES[window.location.hash];
    router.replace(target ?? "/dashboard");
  }, [router]);

  return (
    <div>
      <PageHeader
        title="Compliance"
        description="Taking you to the right screen. Each of these answers one question."
      />
      <div className="flex flex-col gap-2">
        {DESTINATIONS.map((destination) => (
          <Link key={destination.href} href={destination.href} className={CARD_LINK_FOCUS}>
            <Card className="transition-colors hover:border-[var(--border-strong)]">
              <CardContent className="flex items-center justify-between gap-4 pt-6">
                <div>
                  <p className="font-medium text-[var(--fg-default)]">{destination.title}</p>
                  <p className="mt-1 text-sm text-[var(--fg-muted)]">{destination.question}</p>
                </div>
                <ArrowRight
                  className="h-4 w-4 shrink-0 text-[var(--fg-subtle)]"
                  aria-hidden="true"
                />
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}
