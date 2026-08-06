import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import LoginPage from "./page";

vi.mock("@/lib/api", () => ({
  apiFetch: vi.fn(),
  ApiError: class ApiError extends Error {},
}));

const pushMock = vi.fn();
let searchParamsValue = new URLSearchParams();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
  useSearchParams: () => searchParamsValue,
}));

import { apiFetch } from "@/lib/api";

const mockedApiFetch = vi.mocked(apiFetch);

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <LoginPage />
    </QueryClientProvider>,
  );
}

describe("LoginPage — SSO", () => {
  beforeEach(() => {
    mockedApiFetch.mockReset();
    pushMock.mockReset();
    searchParamsValue = new URLSearchParams();
    Object.defineProperty(window, "location", {
      value: { ...window.location, href: "" },
      writable: true,
    });
  });

  it("shows no SSO buttons when no provider is configured", async () => {
    mockedApiFetch.mockImplementation(async (path: string) => {
      if (path === "/api/v1/auth/sso/providers") {
        return [
          { provider: "google", configured: false },
          { provider: "microsoft", configured: false },
        ];
      }
      throw new Error(`Unmocked path: ${path}`);
    });
    renderPage();

    await waitFor(() => expect(mockedApiFetch).toHaveBeenCalled());
    expect(screen.queryByRole("button", { name: /Continue with/ })).not.toBeInTheDocument();
  });

  it("shows a button only for the configured provider and starts the real flow", async () => {
    mockedApiFetch.mockImplementation(async (path: string) => {
      if (path === "/api/v1/auth/sso/providers") {
        return [
          { provider: "google", configured: true },
          { provider: "microsoft", configured: false },
        ];
      }
      if (path === "/api/v1/auth/sso/google/start") {
        return { authorization_url: "https://accounts.google.com/o/oauth2/v2/auth?mock=1" };
      }
      throw new Error(`Unmocked path: ${path}`);
    });
    renderPage();
    const user = userEvent.setup();

    expect(await screen.findByRole("button", { name: "Continue with Google" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Continue with Microsoft" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Continue with Google" }));

    await waitFor(() =>
      expect(mockedApiFetch).toHaveBeenCalledWith("/api/v1/auth/sso/google/start"),
    );
    await waitFor(() =>
      expect(window.location.href).toBe("https://accounts.google.com/o/oauth2/v2/auth?mock=1"),
    );
  });

  it("shows an error banner from the SSO callback's redirect query param", async () => {
    searchParamsValue = new URLSearchParams("error=Something%20went%20wrong");
    mockedApiFetch.mockImplementation(async (path: string) => {
      if (path === "/api/v1/auth/sso/providers") return [];
      throw new Error(`Unmocked path: ${path}`);
    });
    renderPage();

    expect(await screen.findByText("Something went wrong")).toBeInTheDocument();
  });
});
