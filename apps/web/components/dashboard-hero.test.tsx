import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DashboardHero } from "./dashboard-hero";

describe("DashboardHero", () => {
  it("renders the page title as the h1", () => {
    render(<DashboardHero title="Command Center" description="Everything in one view." />);
    expect(screen.getByRole("heading", { level: 1, name: "Command Center" })).toBeInTheDocument();
    expect(screen.getByText("Everything in one view.")).toBeInTheDocument();
  });

  it("shows the AI briefing and a link to the full one when there is a briefing", () => {
    render(
      <DashboardHero
        title="Command Center"
        briefing="Two DPIAs are due for review this week."
        briefingHref="/briefing"
      />,
    );
    expect(screen.getByText("Two DPIAs are due for review this week.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /View full daily briefing/ })).toHaveAttribute(
      "href",
      "/briefing",
    );
  });

  it("collapses to just the greeting when there is no briefing", () => {
    // An empty AI slot would imply the briefing failed rather than that
    // there simply isn't one yet.
    render(<DashboardHero title="Command Center" />);
    expect(screen.queryByText(/AI briefing/)).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /View full daily briefing/ })).not.toBeInTheDocument();
  });

  it("shows a skeleton, not an empty briefing, while loading", () => {
    render(<DashboardHero title="Command Center" loading />);
    expect(screen.queryByText(/AI briefing/)).not.toBeInTheDocument();
  });

  it("keeps every decorative wash out of the accessibility tree", () => {
    const { container } = render(<DashboardHero title="Command Center" briefing="Anything." />);
    for (const node of container.querySelectorAll("[class*='brand-aurora'], [class*='gradient']")) {
      expect(node).toHaveAttribute("aria-hidden", "true");
    }
  });
});
