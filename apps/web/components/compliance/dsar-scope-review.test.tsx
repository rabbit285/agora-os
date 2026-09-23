import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, apiFetch: vi.fn() };
});

import { apiFetch } from "@/lib/api";
import type { DsarScopeSource } from "@/lib/types";

import { DsarScopeReview } from "./dsar-scope-review";

const mockedApiFetch = vi.mocked(apiFetch);
const DSAR_ID = "aaaaaaaa-1111-4222-8333-444444444444";

function source(overrides: Partial<DsarScopeSource> = {}): DsarScopeSource {
  return {
    id: crypto.randomUUID(),
    source_key: "processing_activity:1",
    kind: "processing_activity",
    name: "AI Customer Support",
    reason: "Records customers who contact support.",
    relevance: "high",
    relevance_reason: "Records customers. Wrote from gmail.com, a personal mailbox.",
    linked_systems: ["Zendesk", "AI Support Assistant"],
    potential_sources: [],
    search_capability: "manual_follow_up",
    included: true,
    added_by_user: false,
    record_id: null,
    ...overrides,
  };
}

function mockScope(sources: DsarScopeSource[]) {
  mockedApiFetch.mockImplementation(async (url: string, init?: { method?: string }) => {
    if (url.endsWith("/scope") && init?.method === undefined) return sources as never;
    return {} as never;
  });
}

function renderScope(confirmed = false) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <DsarScopeReview dsarId={DSAR_ID} confirmed={confirmed} />
    </QueryClientProvider>,
  );
}

describe("DsarScopeReview", () => {
  beforeEach(() => {
    mockedApiFetch.mockReset();
  });

  it("shows a low-relevance source rather than hiding it", async () => {
    // The rule the whole panel turns on. A ranking that is wrong costs a
    // click; a filter that is wrong costs a response its completeness.
    mockScope([
      source(),
      source({
        source_key: "processing_activity:2",
        name: "Employee medical-leave administration",
        relevance: "low",
        relevance_reason:
          "Records employees. Wrote from gmail.com, a personal mailbox rather than this organization's domain. Probably unrelated.",
        included: null,
      }),
    ]);

    renderScope();

    expect(
      await screen.findByText("Employee medical-leave administration"),
    ).toBeInTheDocument();
    expect(screen.getByText("Probably unrelated")).toBeInTheDocument();
    // Listed, and left unticked for a person to decide.
    const checkbox = screen.getByRole("checkbox", {
      name: "Employee medical-leave administration",
    });
    expect(checkbox).not.toBeChecked();
  });

  it("shows why each source was suggested and the reasoning behind the ranking", async () => {
    mockScope([source()]);

    renderScope();

    expect(await screen.findByText("Records customers who contact support.")).toBeInTheDocument();
    expect(screen.getByText(/Why this ranking:/)).toBeInTheDocument();
  });

  it("resolves a processing activity to the systems behind it", async () => {
    // A RoPA entry is compliance context, not a database. It says where
    // to look next, and each of those has its own connection state.
    mockScope([
      source({
        potential_sources: [
          {
            name: "Zendesk",
            kind: "ai_system",
            capability: "not_connected",
            detail: "No Veyntra integration is configured for Zendesk.",
          },
          {
            name: "OpenAI",
            kind: "vendor",
            capability: "processor_follow_up",
            detail: "OpenAI processes this data on your behalf.",
          },
        ],
      }),
    ]);

    renderScope();

    expect(await screen.findByText("Potential sources")).toBeInTheDocument();
    expect(screen.getByText("Zendesk — Not connected")).toBeInTheDocument();
    expect(screen.getByText("OpenAI — Processor follow-up")).toBeInTheDocument();
  });

  it("labels searchability separately from relevance", async () => {
    // The bug this replaced: "Veyntra can search this cheaply" was being
    // used as an argument that a source was likely relevant, which made
    // the easiest source to search automatically the most relevant one.
    mockScope([
      source({
        source_key: "internal:identity",
        name: "User accounts",
        kind: "internal",
        // Searchable, and only *possibly* relevant. The two are
        // independent and the screen shows them as such.
        relevance: "possible",
        search_capability: "searchable",
      }),
      source({
        name: "AI Customer Support",
        relevance: "high",
        search_capability: "manual_follow_up",
      }),
    ]);

    renderScope();

    expect(await screen.findByText("Searchable")).toBeInTheDocument();
    expect(screen.getByText("Manual follow-up")).toBeInTheDocument();
    // High relevance on the source Veyntra cannot search; possible on the
    // one it can. Relevance does not track capability.
    expect(screen.getByText("High relevance")).toBeInTheDocument();
    expect(screen.getByText("Possible relevance")).toBeInTheDocument();
  });

  it("preselects by relevance, never by how easy a source is to search", async () => {
    mockScope([
      source({
        source_key: "internal:identity",
        name: "User accounts",
        kind: "internal",
        relevance: "possible",
        search_capability: "searchable",
        included: true,
      }),
      source({
        name: "AI Customer Support",
        relevance: "high",
        search_capability: "manual_follow_up",
        included: true,
      }),
      source({
        source_key: "processing_activity:2",
        name: "Employee medical-leave administration",
        relevance: "low",
        search_capability: "manual_follow_up",
        included: null,
      }),
    ]);

    renderScope();

    await screen.findByText("User accounts");
    expect(screen.getByRole("checkbox", { name: "User accounts" })).toBeChecked();
    // High relevance and unsearchable: still selected, because the
    // decision is about where her data is, not what is convenient.
    expect(screen.getByRole("checkbox", { name: "AI Customer Support" })).toBeChecked();
    expect(
      screen.getByRole("checkbox", { name: "Employee medical-leave administration" }),
    ).not.toBeChecked();
  });

  it("will not confirm while a source is undecided", async () => {
    mockScope([source({ included: null })]);

    renderScope();
    await screen.findByText("AI Customer Support");

    expect(screen.getByRole("button", { name: "Confirm search scope" })).toBeDisabled();
    expect(screen.getByText(/still need a decision/)).toBeInTheDocument();
  });

  it("sends every decision together when the scope is confirmed", async () => {
    mockScope([
      source({ source_key: "a", name: "Included activity" }),
      source({ source_key: "b", name: "Excluded activity", included: false }),
    ]);

    renderScope();
    await screen.findByText("Included activity");

    await userEvent.click(screen.getByRole("button", { name: "Confirm search scope" }));

    await waitFor(() =>
      expect(mockedApiFetch).toHaveBeenCalledWith(
        `/api/v1/compliance/dsars/${DSAR_ID}/scope/confirm`,
        {
          method: "POST",
          body: {
            decisions: [
              { source_key: "a", included: true },
              { source_key: "b", included: false },
            ],
          },
        },
      ),
    );
  });

  it("reports an empty register as a gap, not as a finding about the person", async () => {
    mockScope([]);

    renderScope();

    const note = await screen.findByText(/cannot suggest where to look/);
    expect(note.textContent).toMatch(/not a finding about this person/);
  });

  it("locks the decisions once the scope is confirmed", async () => {
    mockScope([source()]);

    renderScope(true);
    await screen.findByText("AI Customer Support");

    expect(screen.getByRole("checkbox", { name: "AI Customer Support" })).toBeDisabled();
    expect(
      screen.queryByRole("button", { name: "Confirm search scope" }),
    ).not.toBeInTheDocument();
  });
});
