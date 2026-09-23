import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, apiFetch: vi.fn() };
});

import { apiFetch } from "@/lib/api";
import type { DSAR } from "@/lib/types";

import { DsarWorkflow } from "./dsar-workflow";

const mockedApiFetch = vi.mocked(apiFetch);
const ID = "aaaaaaaa-1111-4222-8333-444444444444";

function dsar(overrides: Partial<DSAR> = {}): DSAR {
  return {
    id: ID,
    requester_name: "Jane Doe",
    requester_email: "janedoe@gmail.com",
    request_type: "access",
    status: "received",
    verification_status: "pending",
    verification_method: null,
    verification_notes: null,
    verified_at: null,
    phase: "identity_verification",
    blocked_reason: null,
    scope_confirmed_at: null,
    discovery_findings: null,
    discovery_run_at: null,
    export_generated_at: null,
    received_at: "2027-01-31T09:00:00Z",
    due_at: "2027-02-28T09:00:00Z",
    base_due_at: "2027-02-28T09:00:00Z",
    extension_months: 0,
    extension_reason: null,
    extension_granted_at: null,
    days_remaining: 20,
    overdue: false,
    due_soon: false,
    deadline_label: "20 days left",
    fulfilled_at: null,
    notes: null,
    assigned_to: null,
    created_at: "2027-01-31T09:00:00Z",
    ...overrides,
  };
}

function renderWorkflow(record: DSAR = dsar()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  mockedApiFetch.mockImplementation(async () => ({}) as never);
  return render(
    <QueryClientProvider client={client}>
      <DsarWorkflow dsar={record} />
    </QueryClientProvider>,
  );
}

describe("DsarWorkflow — identity verification", () => {
  beforeEach(() => {
    mockedApiFetch.mockReset();
  });

  it("records the method and the evidence behind it", async () => {
    renderWorkflow();

    await userEvent.type(
      screen.getByPlaceholderText(/Email verification to the address on file/),
      "Email verification to address on file",
    );
    await userEvent.type(
      screen.getByPlaceholderText(/Requester confirmed ownership/),
      "Requester confirmed ownership through verification link.",
    );
    await userEvent.click(screen.getByRole("button", { name: "Mark verified" }));

    await waitFor(() =>
      expect(mockedApiFetch).toHaveBeenCalledWith(
        `/api/v1/compliance/dsars/${ID}/verify-identity`,
        {
          method: "POST",
          body: {
            verified: true,
            method: "Email verification to address on file",
            // The method is a category; the notes are the evidence, and
            // they are what a regulator asking "how did you know it was
            // her?" needs.
            notes: "Requester confirmed ownership through verification link.",
          },
        },
      ),
    );
  });

  it("keeps the record of a failed verification, and says what happens next", () => {
    renderWorkflow(
      dsar({
        verification_status: "failed",
        verification_method: "Email verification to address on file",
        verification_notes: "Verification link was never opened after two attempts.",
        phase: "blocked",
      }),
    );

    expect(screen.getByText(/Verification failed/)).toBeInTheDocument();
    expect(screen.getByText(/never opened after two attempts/)).toBeInTheDocument();
    expect(
      screen.getByText(/Nothing will be searched or disclosed on this request/),
    ).toBeInTheDocument();
  });

  it("says why identity gates everything else", () => {
    renderWorkflow();

    expect(
      screen.getByText(/risks disclosing\s+personal data to whoever asked/),
    ).toBeInTheDocument();
  });

  it("shows the recorded method once verified", () => {
    renderWorkflow(
      dsar({
        verification_status: "verified",
        verification_method: "Email verification to address on file",
        verified_at: "2027-02-02T09:00:00Z",
        phase: "scope_review",
      }),
    );

    expect(
      screen.getByText(/Verified via Email verification to address on file/),
    ).toBeInTheDocument();
  });
});
