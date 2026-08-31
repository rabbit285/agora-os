"use client";

import { DocumentLibrary } from "@/components/compliance/document-library";
import { EvidenceReview } from "@/components/compliance/evidence-review";
import { PageHeader } from "@/components/page-header";

/** Upload, and review what came back.
 *
 * These two were previously buried inside the Compliance page, below the
 * controls and risk register. They are the first thing a new customer
 * does and the thing they return to most, so they get a route of their
 * own rather than an anchor two screens down.
 */
export default function DocumentsPage() {
  return (
    <div>
      <PageHeader
        title="Documents"
        description="Upload a policy and Veyntra reads it, works out what it is, and proposes which controls it evidences."
      />
      <DocumentLibrary />
      <EvidenceReview />
    </div>
  );
}
