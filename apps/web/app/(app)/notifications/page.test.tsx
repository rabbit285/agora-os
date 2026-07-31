import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Notification, NotificationPreference } from "@/lib/types";

import NotificationsPage from "./page";

vi.mock("@/lib/api", () => ({
  apiFetch: vi.fn(),
}));

import { apiFetch } from "@/lib/api";

const mockedApiFetch = vi.mocked(apiFetch);

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <NotificationsPage />
    </QueryClientProvider>,
  );
}

const unreadNotification: Notification = {
  id: "11111111-1111-1111-1111-111111111111",
  title: "Critical security incident assigned to you",
  body: "Needs immediate investigation.",
  link: "/security",
  channels_requested: ["in_app", "email"],
  channels_delivered: ["in_app", "email"],
  read_at: null,
  created_at: new Date().toISOString(),
};

const preferences: NotificationPreference[] = [
  { channel: "email", enabled: true },
  { channel: "slack", enabled: false },
];

describe("NotificationsPage", () => {
  beforeEach(() => {
    mockedApiFetch.mockReset();
  });

  function mockRoutes(notifications: Notification[]) {
    mockedApiFetch.mockImplementation(async (path: string, options?: { method?: string }) => {
      if (path === "/api/v1/notifications") return notifications;
      if (path === "/api/v1/notifications/preferences") return preferences;
      if (options?.method === "POST" && path.endsWith("/read")) {
        return { ...notifications[0], read_at: new Date().toISOString() };
      }
      throw new Error(`Unmocked path: ${path}`);
    });
  }

  it("shows the unread count and lists notifications with their delivered channels", async () => {
    mockRoutes([unreadNotification]);
    renderPage();

    expect(await screen.findByText(/1 unread/)).toBeInTheDocument();
    expect(await screen.findByText("Critical security incident assigned to you")).toBeInTheDocument();
    expect(screen.getByText(/also delivered via email/)).toBeInTheDocument();
  });

  it("shows an empty state when there are no notifications", async () => {
    mockRoutes([]);
    renderPage();

    expect(await screen.findByText("No notifications yet.")).toBeInTheDocument();
  });

  it("marks a notification read when the button is clicked", async () => {
    mockRoutes([unreadNotification]);
    renderPage();
    const user = userEvent.setup();

    const markReadButton = await screen.findByRole("button", { name: "Mark read" });
    await user.click(markReadButton);

    await waitFor(() =>
      expect(mockedApiFetch).toHaveBeenCalledWith(
        `/api/v1/notifications/${unreadNotification.id}/read`,
        { method: "POST" },
      ),
    );
  });

  it("shows channel preferences and lets the user toggle one", async () => {
    mockRoutes([]);
    renderPage();
    const user = userEvent.setup();

    expect(await screen.findByText("email")).toBeInTheDocument();
    expect(screen.getByText("slack")).toBeInTheDocument();
    expect(screen.getAllByText("Not deliverable").length).toBeGreaterThan(0);

    const enabledButton = await screen.findByRole("button", { name: "Enabled" });
    await user.click(enabledButton);

    await waitFor(() =>
      expect(mockedApiFetch).toHaveBeenCalledWith("/api/v1/notifications/preferences", {
        method: "PUT",
        body: { channel: "email", enabled: false },
      }),
    );
  });
});
