/**
 * The one place a document URL is formed in the browser.
 *
 * The server composes hrefs wherever it can. This helper exists for the
 * surfaces that hold a document id and no href, and it is tested against
 * the same two facts the server checks: the route is one the app has, and
 * it is not one the middleware retires.
 */
import { existsSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { DOCUMENT_ROUTE, documentDetailHref } from "./documents";
import { RETIRED_MODULE_PREFIXES } from "@/middleware";

const ID = "da7966ef-1c22-4b0a-9f31-8c5e2d7a41bb";

describe("documentDetailHref", () => {
  it("opens the document at the top when there is nothing to locate", () => {
    // Arriving from the library: no passage, no query, top of the page.
    expect(documentDetailHref(ID)).toBe(`/documents/${ID}`);
  });

  it("carries a passage so the reader lands on it", () => {
    const href = documentDetailHref(ID, { passage: "monitored continuously" });
    const query = new URLSearchParams(href.split("?")[1]);
    expect(query.get("passage")).toBe("monitored continuously");
  });

  it("matches the route the server composes", () => {
    // DOCUMENT_ROUTE in apps/api/app/core/routes.py. If one moves and the
    // other does not, half the product's document links break.
    expect(DOCUMENT_ROUTE).toBe("/documents");
  });

  it("never produces a link into a withdrawn module", () => {
    const href = documentDetailHref(ID);
    for (const prefix of RETIRED_MODULE_PREFIXES) {
      expect(href.startsWith(prefix), `${href} points at retired ${prefix}`).toBe(false);
    }
  });

  it("points at a route file that exists", () => {
    const segment = DOCUMENT_ROUTE.replace("/", "");
    const route = resolve(__dirname, "..", "app", "(app)", segment, "[id]", "page.tsx");
    expect(existsSync(route), `no route file at ${route}`).toBe(true);
  });
});
