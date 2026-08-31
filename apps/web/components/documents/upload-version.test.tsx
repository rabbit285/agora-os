import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, apiFetch: vi.fn() };
});
vi.mock("@/lib/upload", () => ({ uploadFileWithOutcome: vi.fn() }));

import { apiFetch } from "@/lib/api";
import { uploadFileWithOutcome } from "@/lib/upload";

import { UploadNewVersion } from "./upload-version";

const mockedApiFetch = vi.mocked(apiFetch);
const mockedUpload = vi.mocked(uploadFileWithOutcome);

const OLD_FILE = "bbbbbbbb-1111-4222-8333-444444444444";
const NEW_FILE = "cccccccc-1111-4222-8333-444444444444";

function renderButton() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <UploadNewVersion
        supersedesFileId={OLD_FILE}
        documentTitle="AI Governance Policy"
      />
    </QueryClientProvider>,
  );
}

async function pick(file: File) {
  const user = userEvent.setup();
  const input = screen.getByLabelText(
    /upload a new version of AI Governance Policy/i,
  );
  await user.upload(input, file);
}

beforeEach(() => {
  mockedApiFetch.mockReset();
  mockedUpload.mockReset();
  mockedApiFetch.mockResolvedValue({});
  mockedUpload.mockResolvedValue({
    fileId: NEW_FILE,
    status: "new",
    message: null,
  });
});

describe("UploadNewVersion", () => {
  it("names the document it will replace, for the screen reader too", () => {
    renderButton();

    expect(
      screen.getByRole("button", { name: /upload new version/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByLabelText(/upload a new version of AI Governance Policy/i),
    ).toBeInTheDocument();
  });

  it("sends the document being replaced, so nothing has to be guessed later", async () => {
    renderButton();
    await pick(new File(["v2 contents"], "whatever-they-called-it.docx"));

    await waitFor(() => expect(mockedApiFetch).toHaveBeenCalledTimes(1));
    const [path, init] = mockedApiFetch.mock.calls[0];
    expect(path).toBe("/api/v1/compliance/documents/process");
    expect(init?.body).toEqual({
      file_id: NEW_FILE,
      supersedes_file_id: OLD_FILE,
    });
  });

  it("starts no pipeline for bytes the organization already has", async () => {
    mockedUpload.mockResolvedValue({
      fileId: NEW_FILE,
      status: "duplicate",
      message: null,
    });
    renderButton();
    await pick(new File(["identical"], "same.docx"));

    expect(await screen.findByRole("status")).toHaveTextContent(
      /same file you already have/i,
    );
    expect(mockedApiFetch).not.toHaveBeenCalled();
  });

  it("starts no second pipeline while one is already in flight", async () => {
    mockedUpload.mockResolvedValue({
      fileId: NEW_FILE,
      status: "processing",
      message: null,
    });
    renderButton();
    await pick(new File(["identical"], "same.docx"));

    expect(await screen.findByRole("status")).toHaveTextContent(
      /nothing was started twice/i,
    );
    expect(mockedApiFetch).not.toHaveBeenCalled();
  });

  it("says what will happen next rather than claiming it already has", async () => {
    renderButton();
    await pick(new File(["v2"], "v2.docx"));

    const status = await screen.findByRole("status");
    expect(status).toHaveTextContent(/reading it now/i);
    expect(status).toHaveTextContent(/becomes the current version/i);
  });

  it("reports a failure as an alert and says nothing changed", async () => {
    mockedUpload.mockRejectedValue(new Error("network"));
    renderButton();
    await pick(new File(["v2"], "v2.docx"));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /nothing was changed/i,
    );
  });
});
