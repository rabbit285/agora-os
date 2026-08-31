import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, apiFetch: vi.fn() };
});

import { apiFetch, ApiError } from "@/lib/api";

import { LinkCustomerReview } from "./link-customer-review";

const mockedApiFetch = vi.mocked(apiFetch);
const ID = "bbbbbbbb-2222-4333-8444-555555555555";

function renderPanel(
  props: Partial<Parameters<typeof LinkCustomerReview>[0]> = {},
) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <LinkCustomerReview
        questionnaireId={ID}
        suggestedCustomer="Agora Origin"
        suggestionReason='Suggested from the questionnaire title "Agora Origin cusotmer" with 1 descriptive word removed.'
        {...props}
      />
    </QueryClientProvider>,
  );
}

describe("naming the customer a questionnaire came from", () => {
  beforeEach(() => {
    mockedApiFetch.mockReset();
    mockedApiFetch.mockResolvedValue({
      questionnaire_id: ID,
      customer_name: "Agora Origin",
      security_review_id: "cccccccc-3333-4444-8555-666666666666",
      security_review_title: "Agora Origin Security Review",
      review_created: true,
    });
  });

  it("says why the questionnaire has no review", () => {
    renderPanel();
    expect(
      screen.getByText(/no customer is\s+recorded on it/i),
    ).toBeInTheDocument();
  });

  it("offers the suggestion in an editable field, not as a decision", () => {
    renderPanel();
    // A filled-in field the person can see and change — the difference
    // between suggesting a customer and asserting one.
    const field = screen.getByLabelText("Customer") as HTMLInputElement;
    expect(field.value).toBe("Agora Origin");
    // And where that value came from, said out loud.
    expect(screen.getByText(/suggested from the questionnaire title/i)).toBeInTheDocument();
  });

  it("sends what is in the field, not what was suggested", async () => {
    const user = userEvent.setup();
    renderPanel();

    const field = screen.getByLabelText("Customer");
    await user.clear(field);
    await user.type(field, "Agora Origin Ltd");
    await user.click(
      screen.getByRole("button", { name: /set customer and create review/i }),
    );

    await waitFor(() => expect(mockedApiFetch).toHaveBeenCalled());
    expect(mockedApiFetch).toHaveBeenCalledWith(
      `/api/v1/compliance/questionnaires/${ID}/customer`,
      { method: "POST", body: { customer_name: "Agora Origin Ltd" } },
    );
  });

  it("will not submit an empty customer", async () => {
    const user = userEvent.setup();
    renderPanel({ suggestedCustomer: null, suggestionReason: null });

    expect(
      screen.getByRole("button", { name: /set customer and create review/i }),
    ).toBeDisabled();
    // And it says there is nothing to suggest rather than leaving an
    // empty box with no explanation.
    expect(screen.getByText(/nothing to suggest/i)).toBeInTheDocument();

    await user.type(screen.getByLabelText("Customer"), "  ");
    expect(
      screen.getByRole("button", { name: /set customer and create review/i }),
    ).toBeDisabled();
  });

  it("shows the server's reason when the link is refused", async () => {
    mockedApiFetch.mockRejectedValue(
      new ApiError(
        409,
        "Only customer-provided questionnaires belong to a customer security review.",
      ),
    );
    const user = userEvent.setup();
    renderPanel();

    await user.click(
      screen.getByRole("button", { name: /set customer and create review/i }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /only customer-provided questionnaires/i,
    );
  });
});
