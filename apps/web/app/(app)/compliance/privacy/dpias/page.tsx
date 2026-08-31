"use client";

import { DPIASection } from "@/components/compliance/sections/privacy";

/** One record type, on its own route.
 *
 * Split out of the single stacked privacy page so a team with fifty of
 * these can still find one. The section keeps its own list, filters and
 * creation flow; the workspace tabs above it are the layout's.
 */
export default function Page() {
  return <DPIASection />;
}
