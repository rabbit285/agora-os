import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Role } from "@/lib/types";

import RolesSettingsPage from "./page";

vi.mock("@/lib/api", () => ({
  apiFetch: vi.fn(),
}));

import { apiFetch } from "@/lib/api";

const mockedApiFetch = vi.mocked(apiFetch);

const roles: Role[] = [
  { key: "org_admin", name: "Organization Admin", permissions: ["org.settings.manage", "core.tasks.manage"] },
  { key: "read_only", name: "Read Only", permissions: [] },
];

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <RolesSettingsPage />
    </QueryClientProvider>,
  );
}

describe("RolesSettingsPage", () => {
  beforeEach(() => {
    mockedApiFetch.mockReset();
    mockedApiFetch.mockResolvedValue(roles);
  });

  it("lists every role with its permission count", async () => {
    renderPage();

    expect(await screen.findByText("Organization Admin")).toBeInTheDocument();
    expect(await screen.findByText("2 permissions")).toBeInTheDocument();
    expect(await screen.findByText("Read Only")).toBeInTheDocument();
    expect(await screen.findByText("0 permissions")).toBeInTheDocument();
  });

  it("expands a role to show its real permission keys", async () => {
    renderPage();
    const user = userEvent.setup();

    await user.click(await screen.findByText("Organization Admin"));

    expect(await screen.findByText("org.settings.manage")).toBeInTheDocument();
    expect(screen.getByText("core.tasks.manage")).toBeInTheDocument();
  });

  it("shows a deliberate-zero-grant note for a role with no permissions", async () => {
    renderPage();
    const user = userEvent.setup();

    await user.click(await screen.findByText("Read Only"));

    expect(
      await screen.findByText("No permissions granted (deliberate — e.g. Read Only)."),
    ).toBeInTheDocument();
  });
});
