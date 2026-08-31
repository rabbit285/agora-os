/**
 * An audit card, read by a compliance manager.
 *
 * The screenshot that started this showed `control assessed`,
 * `after {"status":"pass"}` and a bare UUID on every row. Everything a
 * reader wants — what changed, to what, by whom, why — was in the
 * database and absent from the screen.
 *
 * These tests hold the line in both directions: nothing raw on the card,
 * and the raw event still reachable underneath.
 */
import { existsSync } from "node:fs";
import { resolve } from "node:path";

import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { AuditEventCard } from "./audit-event-card";
import { RETIRED_MODULE_PREFIXES } from "@/middleware";
import type { AuditEvent } from "@/lib/types";

const UUID = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;
const CONTROL_ID = "fe4d85c5-4852-40bf-bb5a-ec27a1af1332";

function event(overrides: Partial<AuditEvent> = {}): AuditEvent {
  return {
    id: "aaaaaaaa-1111-4222-8333-444444444444",
    title: "Control assessment recorded",
    category: "compliance",
    category_label: "Compliance",
    entity: {
      kind: "Control",
      label: "Monitor AI systems in production",
      href: `/compliance/controls/${CONTROL_ID}`,
      available: true,
    },
    actor_name: "Zach W.",
    actor_kind: "person",
    changes: [{ label: "Status", before: "Needs review", after: "Passed" }],
    reason: "Reviewed operational monitoring evidence and confirmed it is sufficient.",
    created_at: "2026-08-25T02:05:16.000Z",
    action: "compliance.control.assessed",
    object_type: "control",
    object_id: CONTROL_ID,
    actor_user_id: "bbbbbbbb-1111-4222-8333-444444444444",
    actor_email: "zach@example.com",
    before_state: { status: "needs_review" },
    after_state: { status: "pass" },
    correlation_id: "cccccccc-1111-4222-8333-444444444444",
    label: null,
    ...overrides,
  };
}

describe("A. a human control review", () => {
  it("says what happened, to what, and how it changed", () => {
    render(<AuditEventCard event={event()} />);

    expect(screen.getByText("Control assessment recorded")).toBeInTheDocument();
    expect(screen.getByText("Monitor AI systems in production")).toBeInTheDocument();
    expect(screen.getByText("Needs review")).toBeInTheDocument();
    expect(screen.getByText("Passed")).toBeInTheDocument();
  });

  it("names the person who did it", () => {
    render(<AuditEventCard event={event()} />);
    expect(screen.getByText("Zach W.")).toBeInTheDocument();
  });

  it("surfaces the reviewer's own reason", () => {
    render(<AuditEventCard event={event()} />);
    expect(screen.getByText(/Reviewed operational monitoring evidence/)).toBeInTheDocument();
  });

  it("shows no raw JSON and no identifier", () => {
    render(<AuditEventCard event={event()} />);
    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(UUID);
    expect(text).not.toContain("{");
    expect(text).not.toContain('"status"');
    // Nor the machine name of the event.
    expect(text).not.toContain("compliance.control.assessed");
  });
});

describe("B, D, E. the other shapes", () => {
  it("reads a framework reassessment as counts, attributed to the system", () => {
    render(
      <AuditEventCard
        event={event({
          title: "Framework reassessed",
          entity: {
            kind: "Framework",
            label: "ISO 42001",
            href: "/compliance/frameworks/dddddddd-1111-4222-8333-444444444444",
            available: true,
          },
          actor_name: "Veyntra System",
          actor_kind: "system",
          reason: null,
          changes: [
            { label: "Requirements evaluated", before: null, after: "18" },
            { label: "Satisfied", before: null, after: "2" },
            { label: "Awaiting review", before: null, after: "13" },
            { label: "Gaps", before: null, after: "3" },
          ],
        })}
      />
    );

    expect(screen.getByText("Framework reassessed")).toBeInTheDocument();
    expect(screen.getByText("ISO 42001")).toBeInTheDocument();
    expect(screen.getByText("Veyntra System")).toBeInTheDocument();
    expect(screen.getByText("Requirements evaluated:")).toBeInTheDocument();
    expect(screen.getByText("18")).toBeInTheDocument();
  });

  it("attributes a model's work to Veyntra AI", () => {
    render(
      <AuditEventCard
        event={event({
          title: "Remediation plan updated",
          actor_name: "Veyntra AI",
          actor_kind: "ai",
        })}
      />
    );
    expect(screen.getByText("Veyntra AI")).toBeInTheDocument();
  });

  it("says the actor is unavailable rather than inventing one", () => {
    render(
      <AuditEventCard
        event={event({ actor_name: "Actor unavailable", actor_kind: "unknown" })}
      />
    );
    expect(screen.getByText("Actor unavailable")).toBeInTheDocument();
  });
});

describe("F. the technical record", () => {
  it("keeps the raw event one click away", async () => {
    const user = userEvent.setup();
    render(<AuditEventCard event={event()} />);

    await user.click(screen.getByRole("button", { name: "Technical details" }));

    const dialog = await screen.findByRole("dialog");
    // Everything the timeline deliberately hides is here, and only here.
    expect(within(dialog).getByText("compliance.control.assessed")).toBeInTheDocument();
    expect(within(dialog).getByText(CONTROL_ID)).toBeInTheDocument();
    expect(within(dialog).getByText(/"needs_review"/)).toBeInTheDocument();
    expect(within(dialog).getByText(/"pass"/)).toBeInTheDocument();
  });

  it("says the record cannot be edited", async () => {
    const user = userEvent.setup();
    render(<AuditEventCard event={event()} />);
    await user.click(screen.getByRole("button", { name: "Technical details" }));
    expect(
      await screen.findByText(/cannot be edited or deleted/)
    ).toBeInTheDocument();
  });

  it("offers no way to change the record", () => {
    // Immutability is the point of the trail. The redesign must not
    // introduce an edit affordance anywhere on the card.
    render(<AuditEventCard event={event()} />);
    for (const control of screen.getAllByRole("button")) {
      expect(control.textContent).not.toMatch(/edit|delete|remove/i);
    }
  });
});

describe("G. navigation", () => {
  it("links the affected record to a route this app has", () => {
    render(<AuditEventCard event={event()} />);
    const link = screen.getByRole("link", { name: "Monitor AI systems in production" });
    const href = link.getAttribute("href") ?? "";

    expect(href).toBe(`/compliance/controls/${CONTROL_ID}`);
    for (const prefix of RETIRED_MODULE_PREFIXES) {
      expect(href.startsWith(prefix), `${href} points at retired ${prefix}`).toBe(false);
    }
    const segments = href.split("/").filter(Boolean);
    const route = resolve(
      __dirname,
      "..",
      "..",
      "app",
      "(app)",
      ...segments.slice(0, -1),
      "[id]",
      "page.tsx"
    );
    expect(existsSync(route), `no route file at ${route}`).toBe(true);
  });

  it("says a record is gone rather than linking nowhere", () => {
    render(
      <AuditEventCard
        event={event({
          entity: { kind: "Control", label: "Deleted control", href: null, available: false },
        })}
      />
    );
    expect(screen.getByText("Deleted control")).toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "Deleted control" })
    ).not.toBeInTheDocument();
    expect(document.body.textContent ?? "").not.toMatch(UUID);
  });
});

describe("timestamps", () => {
  it("keeps the exact time, with the relative reading as a second line", () => {
    render(<AuditEventCard event={event()} />);
    // An audit entry that says only "2 days ago" cannot be cited.
    const time = document.querySelector("time");
    expect(time?.getAttribute("dateTime")).toBe("2026-08-25T02:05:16.000Z");
    expect(time?.textContent).toMatch(/2026/);
    expect(document.body.textContent).toMatch(/ago|just now/);
  });
});
