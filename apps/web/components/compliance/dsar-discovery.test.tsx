import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, apiFetch: vi.fn() };
});

import { apiFetch } from "@/lib/api";
import type { DsarDiscoveredItem } from "@/lib/types";

import { DsarDiscoveryPanel } from "./dsar-discovery";

const mockedApiFetch = vi.mocked(apiFetch);
const DSAR_ID = "aaaaaaaa-1111-4222-8333-444444444444";

function item(overrides: Partial<DsarDiscoveredItem> = {}): DsarDiscoveredItem {
  return {
    id: crypto.randomUUID(),
    source_key: "internal:identity",
    source_name: "User accounts",
    search_state: "searched_none",
    matches: 0,
    record_ids: [],
    state_detail: null,
    review_decision: "include",
    review_reason: "Searched; no records found.",
    reviewed_at: null,
    sensitivity_flags: [],
    task_id: null,
    ...overrides,
  };
}

function mockDiscovery(items: DsarDiscoveredItem[], plan?: Record<string, unknown>) {
  mockedApiFetch.mockImplementation(async (url: string) => {
    if (url.endsWith("/discovered")) return items as never;
    if (url.endsWith("/discovery-plan"))
      return (plan ?? {
        total: 2,
        connected: 1,
        manual: 1,
        excluded: 0,
        manual_sources: ["AI Customer Support"],
        connected_sources: ["User accounts"],
      }) as never;
    return {} as never;
  });
}

function renderPanel(items: DsarDiscoveredItem[], canSearch = true) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  mockDiscovery(items);
  return render(
    <QueryClientProvider client={client}>
      <DsarDiscoveryPanel
        dsarId={DSAR_ID}
        canSearch={canSearch}
        blockedReason={canSearch ? null : "Confirm the search scope first."}
      />
    </QueryClientProvider>,
  );
}

describe("DsarDiscoveryPanel", () => {
  beforeEach(() => {
    mockedApiFetch.mockReset();
  });

  it("will not let a search run before the scope is confirmed", async () => {
    renderPanel([], false);

    expect(
      await screen.findByRole("button", { name: /Search confirmed data sources/ }),
    ).toBeDisabled();
    expect(screen.getByText("Confirm the search scope first.")).toBeInTheDocument();
  });

  it("shows the plan before the run, naming what it cannot search", async () => {
    renderPanel([]);

    expect(await screen.findByTestId("discovery-plan")).toBeInTheDocument();
    expect(screen.getByText(/1 need manual follow-up/)).toBeInTheDocument();
    expect(
      screen.getByText(/it will raise a follow-up task rather than reporting them as empty/),
    ).toBeInTheDocument();
  });

  it("distinguishes a searched-and-empty source from one nobody searched", async () => {
    // The distinction the five states exist for. Reported as one count,
    // these look identical and mean opposite things to somebody signing
    // a response.
    renderPanel([
      item({ source_name: "User accounts", search_state: "searched_none" }),
      item({
        source_name: "AI Customer Support",
        search_state: "manual_follow_up",
        review_decision: "needs_review",
        state_detail:
          "No connected data source is available for AI Customer Support. Veyntra has not searched it.",
      }),
    ]);

    expect(await screen.findByText("Searched — no records found")).toBeInTheDocument();
    expect(screen.getByText("Manual follow-up required")).toBeInTheDocument();
    expect(screen.getByText(/Veyntra has not searched it/)).toBeInTheDocument();
  });

  it("never renders an unsearchable source as a zero", async () => {
    renderPanel([
      item({
        source_name: "OpenAI",
        search_state: "manual_follow_up",
        matches: 0,
        review_decision: "needs_review",
        state_detail: "No connected data source is available for OpenAI.",
      }),
    ]);

    await screen.findByText("OpenAI");
    // A record count is only shown where a search actually produced one.
    expect(screen.queryByText("0 record(s)")).not.toBeInTheDocument();
  });

  it("surfaces a sensitivity flag as something to look at, not a decision", async () => {
    renderPanel([
      item({
        source_name: "Employee medical-leave administration",
        search_state: "searched_found",
        matches: 3,
        review_decision: "needs_review",
        review_reason: null,
        sensitivity_flags: [
          "May contain special-category health data. Confirm the requester is entitled to all of it before including.",
        ],
      }),
    ]);

    expect(await screen.findByText(/special-category health data/)).toBeInTheDocument();
    // Flagged and left undecided: Article 15(4) is a legal judgement.
    expect(screen.getByText("Needs review")).toBeInTheDocument();
    expect(screen.getByText("3 record(s)")).toBeInTheDocument();
  });

  it("offers no disclosure decision for a source that was never searched", async () => {
    renderPanel([
      item({
        source_name: "Excluded activity",
        search_state: "not_searched",
        review_decision: "exclude",
        review_reason: "Excluded from the confirmed search scope.",
      }),
    ]);

    await screen.findByText("Excluded activity");
    expect(screen.queryByRole("button", { name: "Redact" })).not.toBeInTheDocument();
  });
});
