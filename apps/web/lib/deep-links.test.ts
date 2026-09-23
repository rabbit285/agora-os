/**
 * Every link the product generates must land somewhere.
 *
 * The privacy overview and the review centre exist to say "this needs
 * you, here it is". That promise is only as good as the route on the end
 * of it, and three of them pointed at pages that had never been built:
 * `/compliance/privacy/dpias/{id}`, `/compliance/privacy/data-requests/{id}`
 * and `/compliance/privacy/processing-activities/{id}` all 404'd.
 *
 * A broken alert is worse than a missing one — it teaches people the
 * overdue warnings are decorative, and the next real one gets the same
 * shrug.
 *
 * The hrefs are built in Python and consumed by Next.js, so neither side
 * can check this alone. It lives here because this is the side that
 * knows what routes exist; it reads the API sources as text rather than
 * running them, which is enough to catch a path that leads nowhere.
 */

import { describe, expect, it } from "vitest";
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { join, resolve } from "node:path";

const WEB_APP = resolve(__dirname, "..", "app", "(app)");
const API_COMPLIANCE = resolve(__dirname, "..", "..", "api", "app", "compliance");
const SOURCES = ["privacy_overview.py", "privacy_review.py", "review_center.py"];

/** `href="/compliance/x"` and `href=f"/compliance/x/{y.id}"` alike. */
const HREF = /href=f?"(\/[^"]*)"/g;

function generatedHrefs(): { source: string; href: string }[] {
  const found: { source: string; href: string }[] = [];
  for (const source of SOURCES) {
    const path = join(API_COMPLIANCE, source);
    if (!existsSync(path)) continue;
    const text = readFileSync(path, "utf8");
    for (const match of text.matchAll(HREF)) {
      found.push({ source, href: match[1] });
    }
  }
  return found;
}

/**
 * Whether Next.js has a page for this path.
 *
 * An interpolated segment (`{dpia.id}`) is a dynamic parameter, so the
 * directory has to be a `[id]`-style folder; a literal segment has to
 * match a real directory. Query strings and fragments belong to the
 * page, not the route — `/compliance#controls` is a real page scrolled
 * to a section.
 */
function routeExists(href: string): boolean {
  const path = href.split(/[?#]/)[0].replace(/^\/+|\/+$/g, "");
  if (!path) return true;

  let current = WEB_APP;
  for (const segment of path.split("/")) {
    if (segment.startsWith("{")) {
      const dynamic = readdirSync(current).find(
        (child) => child.startsWith("[") && statSync(join(current, child)).isDirectory(),
      );
      if (!dynamic) return false;
      current = join(current, dynamic);
      continue;
    }
    const candidate = join(current, segment);
    if (!existsSync(candidate) || !statSync(candidate).isDirectory()) return false;
    current = candidate;
  }

  return existsSync(join(current, "page.tsx"));
}

describe("generated deep links", () => {
  it("looks in the right place", () => {
    // Guards the guard: if either tree moves, the checks below would
    // pass by finding nothing rather than by everything resolving.
    expect(existsSync(join(WEB_APP, "compliance", "dpias", "[id]", "page.tsx"))).toBe(true);
    expect(existsSync(API_COMPLIANCE)).toBe(true);
    expect(generatedHrefs().length).toBeGreaterThan(10);
  });

  it("lands every generated href on a real page", () => {
    const broken = generatedHrefs()
      .filter(({ href }) => !routeExists(href))
      .map(({ source, href }) => `${source} → ${href}`);

    expect(broken).toEqual([]);
  });

  it("catches a link to a page that does not exist", () => {
    // The check has to be able to fail, or it is decoration itself.
    expect(routeExists("/compliance/privacy/nonexistent/{id}")).toBe(false);
    expect(routeExists("/compliance/dpias/{dpia.id}")).toBe(true);
    expect(routeExists("/compliance/privacy/transfers/{transfer.id}")).toBe(true);
    // A fragment is a section of a real page, not a route of its own.
    expect(routeExists("/compliance#controls")).toBe(true);
  });
});
