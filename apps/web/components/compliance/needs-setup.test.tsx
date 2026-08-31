import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, apiFetch: vi.fn() };
});

import { apiFetch } from "@/lib/api";
import type { Questionnaire } from "@/lib/types";

import { NeedsSetupPanel } from "./needs-setup";

const mockedApiFetch = vi.mocked(apiFetch);
const ID = "dddddddd-4444-4555-8666-777777777777";

function questionnaire(overrides: Partial<Questionnaire> = {}): Questionnaire {
  return {
    id: ID,
    title: "Do you encrypt customer data at rest?",
    customer_name: null,
    due_at: null,
    can_delete: false,
    delete_blocked_reason: null,
    archived_at: null,
    archived_by: null,
    source: "customer_provided",
    status: "needs_setup",
    status_label: "Needs setup",
    readiness: {
      ready: false,
      needs_setup: true,
      blockers: [
        {
          code: "customer_required",
          message: "Customer required before this questionnaire can be shared.",
        },
      ],
    },
    title_looks_like_a_question: true,
    opportunity_id: null,
    owner_id: null,
    created_at: new Date().toISOString(),
    progress: {
      total: 2,
      approved: 2,
      needs_review: 0,
      draft: 0,
      unanswered: 0,
      percent_complete: 100,
    },
    ...overrides,
  } as Questionnaire;
}

function renderPanel(rows: Questionnaire[]) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <NeedsSetupPanel questionnaires={rows} />
    </QueryClientProvider>,
  );
}

describe("the questionnaires that cannot be shared with anybody yet", () => {
  beforeEach(() => {
    mockedApiFetch.mockReset();
    mockedApiFetch.mockResolvedValue({
      questionnaire_id: ID,
      customer_name: "Agora Origin",
      security_review_id: "eeeeeeee-5555-4666-8777-888888888888",
      security_review_title: "Agora Origin Security Review",
      review_created: true,
    });
  });

  it("shows nothing when nothing needs setup", () => {
    const { container } = renderPanel([
      questionnaire({
        status: "ready_to_share",
        readiness: { ready: true, needs_setup: false, blockers: [] },
      }),
    ]);
    expect(container).toBeEmptyDOMElement();
  });

  it("lists the record and the server's reason, not its own", () => {
    renderPanel([questionnaire()]);

    expect(screen.getByText("1 questionnaire needs setup")).toBeInTheDocument();
    expect(
      screen.getByText("Do you encrypt customer data at rest?"),
    ).toBeInTheDocument();
    // The same sentence the API refuses the transition with.
    expect(
      screen.getByText(
        "Customer required before this questionnaire can be shared.",
      ),
    ).toBeInTheDocument();
  });

  it("counts more than one", () => {
    renderPanel([
      questionnaire(),
      questionnaire({ id: "other", title: "Another one" }),
    ]);
    expect(screen.getByText("2 questionnaires need setup")).toBeInTheDocument();
  });

  it("sets the customer from the row, without opening the record", async () => {
    const user = userEvent.setup();
    renderPanel([questionnaire()]);

    await user.click(
      screen.getByRole("button", {
        name: "Set customer for Do you encrypt customer data at rest?",
      }),
    );
    await user.type(screen.getByLabelText("Customer"), "Agora Origin");
    await user.click(
      screen.getByRole("button", { name: /Set customer and create review/ }),
    );

    await waitFor(() => expect(mockedApiFetch).toHaveBeenCalled());
    expect(mockedApiFetch).toHaveBeenCalledWith(
      `/api/v1/compliance/questionnaires/${ID}/customer`,
      { method: "POST", body: { customer_name: "Agora Origin" } },
    );
  });

  it("will not submit an empty customer", async () => {
    const user = userEvent.setup();
    renderPanel([questionnaire()]);

    await user.click(
      screen.getByRole("button", {
        name: "Set customer for Do you encrypt customer data at rest?",
      }),
    );
    expect(
      screen.getByRole("button", { name: /Set customer and create review/ }),
    ).toBeDisabled();

    await user.type(screen.getByLabelText("Customer"), "   ");
    expect(
      screen.getByRole("button", { name: /Set customer and create review/ }),
    ).toBeDisabled();
    expect(mockedApiFetch).not.toHaveBeenCalled();
  });
});
