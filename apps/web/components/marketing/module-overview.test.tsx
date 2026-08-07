import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { ModuleOverview } from "@/components/marketing/module-overview";

describe("ModuleOverview", () => {
  it("renders all six modules as real links into their /features section", () => {
    render(<ModuleOverview />);
    const expected: Record<string, string> = {
      Compliance: "/features#compliance",
      Security: "/features#security",
      Sales: "/features#sales",
      "Customer Support": "/features#support",
      Automation: "/features#automation",
      "AI Governance": "/features#ai-governance",
    };
    for (const [name, href] of Object.entries(expected)) {
      // Anchored to the start: the whole card is one <a>, so its
      // accessible name is the module name followed by its description
      // and item chips — and at least one card's chip text (Security's
      // "Compliance escalation") contains another module's name as a
      // substring, so an unanchored match would be ambiguous.
      expect(screen.getByRole("link", { name: new RegExp(`^${name}`) })).toHaveAttribute("href", href);
    }
  });

  it("renders each module's description and item chips", () => {
    render(<ModuleOverview />);
    expect(screen.getByText(/RoPA, DPIA, DSAR, controls, policies, vendor risk, audits\./)).toBeInTheDocument();
    expect(screen.getByText("Regulatory intelligence")).toBeInTheDocument();
  });
});
