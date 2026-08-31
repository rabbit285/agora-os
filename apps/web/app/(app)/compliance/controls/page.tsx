"use client";

import { EvidenceLibrary } from "@/components/compliance/evidence-library";
import { ControlsList } from "@/components/compliance/controls-list";
import { RisksSection } from "@/components/compliance/sections/risks";
import { PageHeader } from "@/components/page-header";

/** "Which controls are working, and where are the gaps?"
 *
 * Policies used to sit at the bottom of this page, which made Controls &
 * Risk the policy-management screen as well — and put "No managed
 * policies yet" underneath a list of ten analysed policy documents. Policy
 * governance has a page of its own now, and the records on it are created
 * from the documents rather than typed in again.
 */
export default function ControlsPage() {
  return (
    <div>
      <PageHeader
        title="Controls & Risk"
        description="The measures your organization has in place, what the evidence on file shows about each, and the risks they mitigate."
      />
      <ControlsList />
      <EvidenceLibrary />
      <RisksSection />
    </div>
  );
}
