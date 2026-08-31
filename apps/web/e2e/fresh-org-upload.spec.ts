import { expect, test } from "@playwright/test";

import { API_BASE_URL, signup } from "./helpers";

/** The first thing a customer ever does in the product.
 *
 * A brand-new organization has no controls, no frameworks, nothing. It
 * uploads a policy. That policy has to come back understood — named,
 * classified, governed, searchable — because "which of your controls
 * does this evidence?" is a different question from "what is this?", and
 * only the first one has an answer on day one.
 */

const POLICY = `AI Governance Policy
Version: 1.0
Effective: May 2026

1. Purpose
This policy sets out how the company governs its use of artificial intelligence
across every product and every team that operates one.

7. Monitoring
Production AI systems are reviewed monthly for drift, incidents and material
performance changes by the AI Governance Lead.
`;

async function sha256(text: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function uploadAndProcess(
  request: import("@playwright/test").APIRequestContext,
  name: string,
  text: string,
): Promise<string> {
  const created = await request.post(`${API_BASE_URL}/api/v1/files/upload-url`, {
    data: {
      filename: name,
      content_type: "text/plain",
      size_bytes: text.length,
      classification: "confidential",
      content_hash: await sha256(text),
    },
  });
  expect(created.ok()).toBeTruthy();
  const body = await created.json();
  const put = await request.fetch(body.upload_url, {
    method: "PUT",
    headers: { "Content-Type": "text/plain" },
    data: text,
  });
  expect(put.ok()).toBeTruthy();
  await request.post(`${API_BASE_URL}/api/v1/compliance/documents/process`, {
    data: { file_id: body.file_id },
  });
  return body.file_id;
}

async function waitForAnalysis(
  request: import("@playwright/test").APIRequestContext,
  fileId: string,
): Promise<Record<string, unknown>> {
  for (let attempt = 0; attempt < 60; attempt += 1) {
    const response = await request.get(`${API_BASE_URL}/api/v1/compliance/documents`);
    const rows = await response.json();
    const row = Array.isArray(rows) ? rows.find((d) => d.id === fileId) : null;
    if (row?.document_id && row.processing_status === "ready") return row;
    await new Promise((resolve) => setTimeout(resolve, 2000));
  }
  throw new Error("document never finished processing");
}

test("a fresh organization's first upload comes back understood", async ({ page }) => {
  test.slow();
  await signup(page, "freshorg");

  // No framework adopted, so no controls. This is the state every trial
  // account is in.
  const controls = await page.request.get(`${API_BASE_URL}/api/v1/compliance/controls`);
  const controlList = await controls.json();
  expect(Array.isArray(controlList) ? controlList : (controlList.items ?? [])).toHaveLength(
    0,
  );

  const fileId = await uploadAndProcess(page.request, "AI_Governance_Policy.docx", POLICY);
  const row = await waitForAnalysis(page.request, fileId);

  // §13, read from the API the page renders from.
  expect(row.document_type, "the document must know what it is").toBeTruthy();
  expect(row.processing_status).toBe("ready");
  expect(row.index_status).toBe("indexed");
  expect(row.mapping_state).toBe("no_controls");
  expect(row.policy_title, "a policy gets its governance record").toBeTruthy();
  expect(row.policy_status).toBe("needs_review");

  await page.goto("/documents");

  // §9: the row is complete, not a filename with blanks after it.
  // `exact`, because the row also links to the Managed Policy it
  // created — which is itself the thing that used to be missing.
  await expect(
    page.getByRole("link", { name: "AI Governance Policy", exact: true }),
  ).toBeVisible();
  await expect(page.getByText("Analyzed")).toBeVisible();
  await expect(page.getByText("Indexed for Copilot")).toBeVisible();

  // §4: the governance record, reachable from the document that made it.
  await expect(
    page.getByRole("link", { name: /policy detected.*needs governance review/i }),
  ).toBeVisible();

  // §5: nothing here reads as a failure or a negative finding.
  await expect(
    page.getByText(/evidence mapping starts when you adopt a framework/i),
  ).toBeVisible();
  await expect(page.getByText(/no control matches proposed/i)).toHaveCount(0);
  await expect(page.getByText(/failed/i)).toHaveCount(0);

  await page.screenshot({
    path: "test-results/local-smoke/fresh-org-documents.png",
    fullPage: true,
  });

  // The Managed Policy exists and is reachable, on an organization that
  // has adopted nothing.
  await page.goto("/compliance/policies");
  await expect(page.getByText("AI Governance Policy").first()).toBeVisible();
  await page.screenshot({
    path: "test-results/local-smoke/fresh-org-policies.png",
    fullPage: true,
  });
});
