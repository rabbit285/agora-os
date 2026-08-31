"use client";

import {
  AuditsSection,
  QuestionnairesSection,
  SecurityReviewsSection,
} from "@/components/compliance/sections/assessments";
import { PageHeader } from "@/components/page-header";

/** "What is being assessed, by us and by our customers?" */
export default function AssessmentsPage() {
  return (
    <div>
      <PageHeader
        title="Assessments"
        description="Internal questionnaires and audits, and the security reviews your customers ask you to complete before they sign."
      />
      <QuestionnairesSection />
      <AuditsSection />
      <SecurityReviewsSection />
    </div>
  );
}
