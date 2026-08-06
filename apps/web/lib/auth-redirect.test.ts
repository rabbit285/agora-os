import { describe, expect, it } from "vitest";

import { isSafeRedirectTarget } from "./auth-redirect";

describe("isSafeRedirectTarget", () => {
  it("accepts a plain same-origin absolute path", () => {
    expect(isSafeRedirectTarget("/dashboard")).toBe(true);
    expect(isSafeRedirectTarget("/sales/lead-finder")).toBe(true);
    expect(isSafeRedirectTarget("/settings/users?tab=invites")).toBe(true);
  });

  it("rejects null, undefined, and empty values", () => {
    expect(isSafeRedirectTarget(null)).toBe(false);
    expect(isSafeRedirectTarget(undefined)).toBe(false);
    expect(isSafeRedirectTarget("")).toBe(false);
  });

  it("rejects a value that isn't an absolute path", () => {
    expect(isSafeRedirectTarget("dashboard")).toBe(false);
    expect(isSafeRedirectTarget("evil.com")).toBe(false);
  });

  it("rejects protocol-relative URLs", () => {
    expect(isSafeRedirectTarget("//evil.com")).toBe(false);
    expect(isSafeRedirectTarget("//evil.com/dashboard")).toBe(false);
  });

  it("rejects a leading-backslash variant of the protocol-relative attack", () => {
    expect(isSafeRedirectTarget("/\\evil.com")).toBe(false);
  });

  it("rejects an absolute URL to another origin", () => {
    expect(isSafeRedirectTarget("https://evil.com")).toBe(false);
    expect(isSafeRedirectTarget("http://evil.com/dashboard")).toBe(false);
  });

  it("rejects a smuggled absolute URL after a leading slash", () => {
    expect(isSafeRedirectTarget("/https://evil.com")).toBe(false);
  });

  it("rejects a javascript: URI", () => {
    expect(isSafeRedirectTarget("javascript:alert(1)")).toBe(false);
  });
});
