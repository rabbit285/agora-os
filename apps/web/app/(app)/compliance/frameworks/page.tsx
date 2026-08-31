"use client";

import { FrameworkApplicability } from "@/components/compliance/framework-applicability";
import { ReadinessPanel } from "@/components/compliance/readiness-panel";
import { PageHeader } from "@/components/page-header";

/** "Which frameworks apply, and how ready are we?"
 *
 * The raw catalog list is deliberately absent. It was a third rendering
 * of the same eight frameworks on one screen — after readiness and after
 * applicability — as bare chips carrying no state, beside a permanently
 * open form for creating custom ones. Adoption happens in "What applies
 * to us"; once adopted, a framework appears in "Where you stand" with a
 * link to its detail. A list that only repeated the names was answering
 * a question nobody had.
 *
 * Two different questions, in that order, kept visually separate:
 * applicability is about the facts you declared and settles whether an
 * obligation binds you at all; readiness is about the evidence on file
 * and settles how much of it you can show. Running them together in one
 * badge — "Applicable · Awaiting review" — was asking the reader to hold
 * two unrelated ideas in one glance.
 */
export default function FrameworksPage() {
  return (
    <div>
      <PageHeader
        title="Frameworks"
        description="Which regulations and standards apply to your organization, and how much of each you can currently evidence."
      />
      <ReadinessPanel />
      <FrameworkApplicability />
    </div>
  );
}
