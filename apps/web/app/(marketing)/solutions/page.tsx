import type { Metadata } from "next";
import { Bot, ClipboardCheck, FileSearch, Scale, ShieldCheck, Users } from "lucide-react";

import { CustomerTypeSection } from "@/components/marketing/customer-type-section";
import { PageHero } from "@/components/marketing/page-hero";
import { WorkflowExample } from "@/components/marketing/workflow-example";

export const metadata: Metadata = {
  title: "Solutions — Veyntra",
  description:
    "Who Veyntra is for, which regulations it covers, and what it actually does with the documents you already have.",
  alternates: { canonical: "/solutions" },
};

/** Roles that map to capabilities the product genuinely has. Each
 * description names a real screen or behaviour rather than a benefit in
 * the abstract — promising outcomes the software cannot demonstrate is
 * the fastest way to lose a compliance buyer, who will test them. */
const AUDIENCES = [
  {
    icon: ShieldCheck,
    title: "Compliance and privacy leads",
    description:
      "Adopt a framework and its control set is built for you. Upload the policies you already have and review the mappings Veyntra proposes, each quoting the passage it relied on.",
  },
  {
    icon: Users,
    title: "Teams without a GRC function",
    description:
      "The work that usually needs a dedicated analyst — reading documents, deciding which control they support, recording the link — is done for you. You approve, and keep the accountability.",
  },
  {
    icon: Bot,
    title: "Organizations deploying AI",
    description:
      "Keep an inventory of your AI systems, screen them against the EU AI Act prohibited and high-risk criteria, and hold the DPIAs and human-oversight evidence that go with them.",
  },
  {
    icon: Scale,
    title: "Anyone facing an audit",
    description:
      "A readiness score that shows its arithmetic, gaps that name the evidence they need, and a trail recording who approved which mapping and when.",
  },
];

const FRAMEWORKS = [
  {
    name: "GDPR",
    detail:
      "Articles 5, 30, 33 and 35, with DPIA screening against Art. 35(3) and the nine EDPB criteria.",
  },
  {
    name: "EU AI Act",
    detail:
      "Prohibited, high-risk and transparency screening, with the reasoning shown and uncertainties flagged for human review.",
  },
  {
    name: "ISO 27001",
    detail:
      "Annex A controls, with certification claims gated behind real attestation evidence.",
  },
  {
    name: "NIS2",
    detail: "Incident and risk-management obligations mapped to the controls you already hold.",
  },
  {
    name: "DORA",
    detail:
      "Operational resilience and third-party risk, with vendor reviews recorded against evidence.",
  },
  {
    name: "SOC 2",
    detail:
      "Trust services criteria, evidenced from the same document library as everything else.",
  },
];

const COMMITMENTS = [
  {
    icon: FileSearch,
    text: "Cite a passage that is not in your document. Every quote is checked against the source, and one that cannot be found is never offered for approval.",
  },
  {
    icon: ClipboardCheck,
    text: "Decide your compliance position with a model. Assessments are computed from the evidence you approved, so the same inputs always produce the same result.",
  },
  {
    icon: ShieldCheck,
    text: "Claim a certification you cannot evidence. Publishing “certified” requires an attestation document; it is never inferred from your controls.",
  },
  {
    icon: Scale,
    text: "Turn missing evidence into a legal verdict. An unevidenced requirement is reported as exactly that, never as a violation.",
  },
];

export default function SolutionsPage() {
  return (
    <div>
      <PageHero
        eyebrow="Solutions"
        title="Compliance work, done by reading the documents you"
        accent="already have"
        description="Veyntra is built for organizations held to real regulations that do not have a large compliance team to satisfy them."
      />

      <div className="mx-auto max-w-[var(--content-max-width)] px-4 pb-24 sm:px-6 lg:px-8">
        <div className="mx-auto grid max-w-5xl gap-5 sm:grid-cols-2">
          {AUDIENCES.map((audience) => (
            <div
              key={audience.title}
              className="rounded-[var(--radius-lg)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-6"
            >
              <span className="inline-flex h-10 w-10 items-center justify-center rounded-[var(--radius-md)] bg-[var(--brand-primary-subtle)]">
                <audience.icon
                  className="h-5 w-5 text-[var(--brand-primary)]"
                  aria-hidden="true"
                />
              </span>
              <h2 className="mt-4 text-lg font-semibold text-[var(--fg-default)]">
                {audience.title}
              </h2>
              <p className="mt-2 text-sm leading-relaxed text-[var(--fg-muted)]">
                {audience.description}
              </p>
            </div>
          ))}
        </div>

        {/* Named regulations with a specific article or obligation against
            each, because "supports GDPR" is a claim every tool in this
            category makes and none of them are held to. */}
        <div className="mx-auto mt-20 max-w-5xl">
          <div className="mx-auto max-w-2xl text-center">
            <p className="flex items-center justify-center gap-2 text-xs font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
              <span
                aria-hidden="true"
                className="h-3 w-1 rounded-full bg-[image:var(--gradient-arc-teal)]"
              />
              Coverage
            </p>
            <h2 className="mt-3 text-[length:var(--text-3xl)] font-semibold tracking-tight text-[var(--fg-default)]">
              The frameworks you are held to
            </h2>
          </div>
          <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {FRAMEWORKS.map((framework) => (
              <div
                key={framework.name}
                className="rounded-[var(--radius-lg)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-5"
              >
                <h3 className="text-sm font-semibold text-[var(--fg-default)]">
                  {framework.name}
                </h3>
                <p className="mt-1.5 text-sm leading-relaxed text-[var(--fg-muted)]">
                  {framework.detail}
                </p>
              </div>
            ))}
          </div>
        </div>

        <div className="mx-auto mt-20 max-w-2xl text-center">
          <p className="flex items-center justify-center gap-2 text-xs font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
            <span
              aria-hidden="true"
              className="h-3 w-1 rounded-full bg-[image:var(--gradient-arc-teal)]"
            />
            In practice
          </p>
          <h2 className="mt-3 text-[length:var(--text-3xl)] font-semibold tracking-tight text-[var(--fg-default)]">
            What happens after you upload one document
          </h2>
          <p className="mt-3 text-sm leading-relaxed text-[var(--fg-muted)]">
            Each step is a real transition in the product, not an illustration of a roadmap.
          </p>
          <div className="mt-8 flex flex-col gap-4 text-left">
            <WorkflowExample
              steps={[
                { module: "Document", label: "Document" },
                { module: "Evidence", label: "Evidence" },
              ]}
              description="The document is read and classified, and Veyntra proposes which controls it evidences — quoting the passage it relied on, and checking that quote against your file before you ever see it."
            />
            <WorkflowExample
              steps={[
                { module: "Approval", label: "Approval" },
                { module: "Assessment", label: "Assessment" },
              ]}
              description="Approving a mapping marks the control for reassessment rather than silently re-grading it. The previous conclusion stays on the record until someone runs the assessment again."
            />
            <WorkflowExample
              steps={[
                { module: "Gap", label: "Gap" },
                { module: "Task", label: "Task" },
              ]}
              description="Whatever the evidence does not cover becomes a gap naming the evidence it needs, and a dated task linked back to the requirement and control that produced it."
            />
          </div>
        </div>

        {/* The commitments a compliance buyer will test during a trial.
            Stated as refusals because that is what makes them checkable. */}
        <div className="mx-auto mt-20 max-w-3xl rounded-[var(--radius-lg)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-8">
          <h2 className="text-lg font-semibold text-[var(--fg-default)]">
            What Veyntra will not do
          </h2>
          <ul className="mt-4 flex flex-col gap-3">
            {COMMITMENTS.map((commitment) => (
              <li key={commitment.text} className="flex items-start gap-3">
                <commitment.icon
                  className="mt-0.5 h-4 w-4 shrink-0 text-[var(--brand-primary)]"
                  aria-hidden="true"
                />
                <span className="text-sm leading-relaxed text-[var(--fg-muted)]">
                  {commitment.text}
                </span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      <CustomerTypeSection />
    </div>
  );
}
