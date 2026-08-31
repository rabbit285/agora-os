import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, apiFetch: vi.fn() };
});

import { apiFetch, ApiError } from "@/lib/api";

import { LifecycleMenu } from "./lifecycle-menu";

const mockedApiFetch = vi.mocked(apiFetch);
const ID = "aaaaaaaa-1111-4222-8333-444444444444";

function renderMenu(props: Partial<Parameters<typeof LifecycleMenu>[0]> = {}) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <LifecycleMenu
        kind="questionnaire"
        id={ID}
        title="Agora Origin Customer Security Questionnaire"
        canDelete
        {...props}
      />
    </QueryClientProvider>,
  );
}

/** Render the row's menu and open it. Renders unless a test already
 * rendered its own variant. */
async function openMenu(props: Partial<Parameters<typeof LifecycleMenu>[0]> = {}) {
  const user = userEvent.setup();
  if (!screen.queryByRole("button", { name: /actions for/i })) {
    renderMenu(props);
  }
  await user.click(screen.getByRole("button", { name: /actions for/i }));
  return user;
}

beforeEach(() => {
  mockedApiFetch.mockReset();
  mockedApiFetch.mockResolvedValue({});
});

describe("LifecycleMenu", () => {
  it("hides destructive actions behind an overflow menu", () => {
    renderMenu();

    // Nothing destructive on the row itself.
    expect(screen.queryByRole("menuitem", { name: /delete/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /actions for/i })).toBeInTheDocument();
  });

  it("offers Archive and Delete draft for a record nothing has happened to", async () => {
    await openMenu();

    expect(await screen.findByRole("menuitem", { name: /archive/i })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /delete draft/i })).toBeInTheDocument();
  });

  it("never fires straight from the menu", async () => {
    const user = await openMenu();

    await user.click(await screen.findByRole("menuitem", { name: /delete draft/i }));

    expect(mockedApiFetch).not.toHaveBeenCalled();
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
  });

  it("says what deleting will remove, and that it cannot be undone", async () => {
    const user = await openMenu();
    await user.click(await screen.findByRole("menuitem", { name: /delete draft/i }));

    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent(/delete questionnaire\?/i);
    expect(dialog).toHaveTextContent("Agora Origin Customer Security Questionnaire");
    expect(dialog).toHaveTextContent(/draft questions and answers/i);
    expect(dialog).toHaveTextContent(/cannot be undone/i);
  });

  it("deletes only after the confirmation is clicked", async () => {
    const user = await openMenu();
    await user.click(await screen.findByRole("menuitem", { name: /delete draft/i }));
    await user.click(
      await screen.findByRole("button", { name: /^delete draft$/i }),
    );

    await waitFor(() => expect(mockedApiFetch).toHaveBeenCalledTimes(1));
    expect(mockedApiFetch.mock.calls[0][0]).toBe(
      `/api/v1/compliance/questionnaires/${ID}`,
    );
    expect(mockedApiFetch.mock.calls[0][1]?.method).toBe("DELETE");
  });

  it("cancels without touching anything", async () => {
    const user = await openMenu();
    await user.click(await screen.findByRole("menuitem", { name: /delete draft/i }));
    await user.click(await screen.findByRole("button", { name: /cancel/i }));

    expect(mockedApiFetch).not.toHaveBeenCalled();
  });

  it("promises that archiving keeps everything", async () => {
    const user = await openMenu();
    await user.click(await screen.findByRole("menuitem", { name: /archive/i }));

    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent(/removed from active work/i);
    expect(dialog).toHaveTextContent(/answers, approvals, source citations and audit history/i);
    expect(dialog).not.toHaveTextContent(/cannot be undone/i);
  });

});

describe("LifecycleMenu when the record has history", () => {
  it("replaces Delete with the reason it is unavailable", async () => {
    renderMenu({
      canDelete: false,
      deleteBlockedReason:
        "It has 3 answers somebody has decided on. Archive it instead.",
    });
    await openMenu();

    expect(await screen.findByRole("menuitem", { name: /archive/i })).toBeInTheDocument();
    expect(
      screen.queryByRole("menuitem", { name: /delete/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText(/3 answers somebody has decided on/i),
    ).toBeInTheDocument();
  });

  it("surfaces a server refusal rather than failing silently", async () => {
    mockedApiFetch.mockRejectedValue(
      new ApiError(
        409,
        "It has 3 answers somebody has decided on. Archive it instead.",
      ),
    );
    const user = await openMenu();
    await user.click(await screen.findByRole("menuitem", { name: /delete draft/i }));
    await user.click(await screen.findByRole("button", { name: /^delete draft$/i }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/archive it instead/i);
  });
});

describe("LifecycleMenu for an archived record", () => {
  it("offers Restore instead of Archive", async () => {
    renderMenu({ archived: true, canDelete: false });
    await openMenu();

    expect(await screen.findByRole("menuitem", { name: /restore/i })).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: /^archive$/i })).not.toBeInTheDocument();
  });

  it("restores without a confirmation — nothing is being destroyed", async () => {
    renderMenu({ archived: true, canDelete: false });
    const user = await openMenu();
    await user.click(await screen.findByRole("menuitem", { name: /restore/i }));

    await waitFor(() => expect(mockedApiFetch).toHaveBeenCalledTimes(1));
    expect(mockedApiFetch.mock.calls[0][0]).toBe(
      `/api/v1/compliance/questionnaires/${ID}/restore`,
    );
  });
});

describe("LifecycleMenu for audits", () => {
  it("uses the audit's own words", async () => {
    renderMenu({ kind: "audit", title: "ISO 27001 surveillance", canDelete: true });
    const user = await openMenu();
    await user.click(await screen.findByRole("menuitem", { name: /archive/i }));

    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent(/archive audit\?/i);
    expect(dialog).toHaveTextContent(/findings, remediation and audit history/i);
  });

  it("calls the audits endpoint", async () => {
    renderMenu({ kind: "audit", title: "Planned audit", canDelete: true });
    const user = await openMenu();
    await user.click(await screen.findByRole("menuitem", { name: /archive/i }));
    await user.click(await screen.findByRole("button", { name: /^archive$/i }));

    await waitFor(() => expect(mockedApiFetch).toHaveBeenCalledTimes(1));
    expect(mockedApiFetch.mock.calls[0][0]).toBe(
      `/api/v1/compliance/audits/${ID}/archive`,
    );
  });
});
