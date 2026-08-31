import { expect, test } from "@playwright/test";

import { API_BASE_URL, signup } from "./helpers";

/** Uploading a revision of a document you already have.
 *
 * The whole promise of this feature is that nobody renames a file to
 * `AI_Governance_Policy_v2.docx` to be understood. So the revision here
 * is uploaded under a name that shares no version marker with the
 * original, and the product still has to work out what it is — and then
 * *ask*, rather than merge on its own judgement.
 */

const V1 = `AI Governance Policy
Version: 1.0
Effective: May 2026

1. Purpose
This policy sets out how the company governs its use of artificial intelligence
across every product and every team that operates one.

7. Monitoring
AI systems should be monitored.

10. Retention
Model training data is retained for two years and then deleted.
`;

const V2 = `AI Governance Policy
Version: 2.0
Effective: August 2026

1. Purpose
This policy sets out how the company governs its use of artificial intelligence
across every product and every team that operates one.

7. Monitoring
Production AI systems are reviewed monthly for drift, incidents and material
performance changes by the AI Governance Lead.

8. Human oversight
Every production AI system has a named human owner who can halt it.
`;

/** Upload through the real API the browser uses, then wait for the
 * pipeline to finish. Driving the file picker would test the file
 * picker; what this spec is about is what the pages say afterwards. */
async function uploadAndProcess(
  request: import("@playwright/test").APIRequestContext,
  name: string,
  text: string,
): Promise<{ fileId: string; status: string }> {
  const hash = await sha256(text);
  const created = await request.post(`${API_BASE_URL}/api/v1/files/upload-url`, {
    data: {
      filename: name,
      content_type: "text/plain",
      size_bytes: text.length,
      classification: "confidential",
      content_hash: hash,
    },
  });
  expect(created.ok()).toBeTruthy();
  const body = await created.json();

  if (body.upload_url) {
    const put = await request.fetch(body.upload_url, {
      method: "PUT",
      headers: { "Content-Type": "text/plain" },
      data: text,
    });
    expect(put.ok()).toBeTruthy();
    await request.post(`${API_BASE_URL}/api/v1/compliance/documents/process`, {
      data: { file_id: body.file_id },
    });
  }
  return { fileId: body.file_id, status: body.status };
}

async function sha256(text: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function waitForDocument(
  request: import("@playwright/test").APIRequestContext,
  fileId: string,
): Promise<{ documentId: string }> {
  for (let attempt = 0; attempt < 60; attempt += 1) {
    const response = await request.get(`${API_BASE_URL}/api/v1/compliance/documents`);
    const rows = await response.json();
    const row = Array.isArray(rows) ? rows.find((d) => d.id === fileId) : null;
    if (row?.document_id) return { documentId: row.document_id };
    await new Promise((resolve) => setTimeout(resolve, 2000));
  }
  throw new Error("document never finished processing");
}

test("a revision under a different filename is proposed, not merged", async ({ page }) => {
  test.slow();
  await signup(page, "versions");

  const first = await uploadAndProcess(page.request, "AI Governance Policy.docx", V1);
  await waitForDocument(page.request, first.fileId);

  // §32: the same bytes again are recognised as what they are.
  const again = await uploadAndProcess(page.request, "AI Governance Policy.docx", V1);
  expect(again.status).toBe("duplicate");
  expect(again.fileId).toBe(first.fileId);

  // §34: a revision whose filename gives nothing away.
  const second = await uploadAndProcess(page.request, "Updated_AI_Governance_August.docx", V2);
  const { documentId } = await waitForDocument(page.request, second.fileId);

  await page.goto(`/documents/${documentId}`);

  // §7: asked, with reasons, and nothing linked yet.
  const question = page.getByRole("heading", {
    name: /is this a new version of AI Governance Policy\?/i,
  });
  await expect(question).toBeVisible();
  await page.screenshot({
    path: "test-results/local-smoke/version-proposed.png",
    fullPage: true,
  });
  await expect(page.getByText(/nothing has been linked yet/i)).toBeVisible();
  await expect(page.getByRole("button", { name: /treat as separate document/i })).toBeEnabled();

  // The reasons are the point: a proposal you cannot check is one you
  // cannot disagree with.
  const banner = page.locator("section", { has: question });
  await expect(banner.locator("li").first()).toBeVisible();

  // §33: accepting it leaves one logical document with two versions.
  await page.getByRole("button", { name: /use as a new version/i }).click();
  await expect(question).toBeHidden({ timeout: 30_000 });

  await expect(page.getByRole("heading", { name: /version history/i })).toBeVisible();
  await expect(page.getByText("2 versions")).toBeVisible();
  await expect(page.getByText("Superseded")).toBeVisible();

  // §25: what actually changed, in sections rather than lines. Scoped to
  // the comparison, so a section heading in the document body below
  // cannot stand in for one the diff was supposed to report. The panel
  // only mounts once the detail refetch shows two versions, so it gets
  // longer than the default to appear.
  const compare = page.locator("section", {
    has: page.getByRole("heading", { name: /what changed/i }),
  });
  await expect(compare).toBeVisible();
  await expect(compare.getByText(/substantially rewritten/i)).toBeVisible({
    timeout: 30_000,
  });
  // `exact` because each section is named twice in the panel — once as
  // its heading, once inside the sentence describing what happened to it.
  await expect(compare.getByText("7. Monitoring", { exact: true })).toBeVisible();
  await expect(compare.getByText("8. Human oversight", { exact: true })).toBeVisible();
  await expect(compare.getByText(/no longer in the document/i)).toBeVisible();
  // The wording on both sides — what a reviewer is actually deciding about.
  await expect(compare.getByText("AI systems should be monitored.")).toBeVisible();
  await page.screenshot({
    path: "test-results/local-smoke/version-accepted.png",
    fullPage: true,
  });

  // §9: the library lists the document once, not once per upload.
  await page.goto("/documents");
  await expect(page.getByText("2 versions")).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Updated AI Governance August" }),
  ).toHaveCount(1);
  // The superseded version is history, not a second row in the library.
  await expect(
    page.getByRole("link", { name: "AI Governance Policy", exact: true }),
  ).toHaveCount(0);
});

test("an unrelated policy is never proposed as a version", async ({ page }) => {
  test.slow();
  await signup(page, "unrelated");

  const policy = await uploadAndProcess(page.request, "AI Governance Policy.docx", V1);
  await waitForDocument(page.request, policy.fileId);

  const travel = await uploadAndProcess(
    page.request,
    "Employee_Travel_Policy.docx",
    `Employee Travel Policy
Version: 1.0

1. Purpose
This policy sets out how employees book and claim travel, what classes of
travel are permitted, and the approval each requires before booking.

2. Booking
Travel is booked through the corporate travel desk wherever possible.
`,
  );
  const { documentId } = await waitForDocument(page.request, travel.fileId);

  await page.goto(`/documents/${documentId}`);

  // Both are policies, both say "Version: 1.0", both open with a Purpose
  // section. None of that makes one a revision of the other.
  await expect(page.getByRole("heading", { name: /is this a new version of/i })).toHaveCount(0);

  // Two rows, because they really are two documents.
  await page.goto("/documents");
  await expect(
    page.getByRole("link", { name: "Employee Travel Policy", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "AI Governance Policy", exact: true }),
  ).toBeVisible();
});
