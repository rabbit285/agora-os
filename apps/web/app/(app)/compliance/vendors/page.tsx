"use client";

import {
  TrustCenterSection,
  VendorsSection,
} from "@/components/compliance/sections/vendors";
import { PageHeader } from "@/components/page-header";

/** "Which third parties create compliance risk?" */
export default function VendorsPage() {
  return (
    <div>
      <PageHeader
        title="Vendors & Trust"
        description="The third parties that touch your data, and what you publish to your own customers about how you handle theirs."
      />
      <VendorsSection />
      <TrustCenterSection />
    </div>
  );
}
