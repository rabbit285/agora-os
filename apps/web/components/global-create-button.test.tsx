import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { GlobalCreateButton } from "./global-create-button";

vi.mock("@/lib/api", () => ({
  apiFetch: vi.fn(),
}));

const pushMock = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
}));

import { apiFetch } from "@/lib/api";

const mockedApiFetch = vi.mocked(apiFetch);

function renderButton() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <GlobalCreateButton />
    </QueryClientProvider>,
  );
}

describe("GlobalCreateButton", () => {
  beforeEach(() => {
    mockedApiFetch.mockReset();
    pushMock.mockReset();
  });

  it("renders nothing while permissions are loading or empty", async () => {
    mockedApiFetch.mockResolvedValue([]);
    const { container } = renderButton();
    await waitFor(() => expect(mockedApiFetch).toHaveBeenCalled());
    expect(container.firstChild).toBeNull();
  });

  it("only lists options the current user has permission to create", async () => {
    mockedApiFetch.mockResolvedValue(["core.tasks.manage"]);
    renderButton();
    const user = userEvent.setup();

    const button = await screen.findByRole("button", { name: "Create ▾" });
    await user.click(button);

    expect(await screen.findByText("Task")).toBeInTheDocument();
    expect(screen.queryByText("Lead")).not.toBeInTheDocument();
    expect(screen.queryByText("Workflow")).not.toBeInTheDocument();
  });

  it("navigates to the entity's owning module page when an option is clicked", async () => {
    mockedApiFetch.mockResolvedValue(["automation.workflows.manage"]);
    renderButton();
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Create ▾" }));
    await user.click(await screen.findByText("Workflow"));

    expect(pushMock).toHaveBeenCalledWith("/automation");
  });
});
