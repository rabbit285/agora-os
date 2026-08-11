import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Logo, LogoMark } from "./logo";

/** Contrast ratio per WCAG 2.1, used to prove the brand *text* gradient is
 * actually readable. The decorative gradient is not: --brand-cyan is
 * 1.81:1 on white, well under the 3:1 floor for large text, which is the
 * whole reason a separate --gradient-brand-text exists. A test rather than
 * a comment because the two gradients look interchangeable in source and
 * swapping them would silently ship an illegible headline. */
function contrastRatio(hexA: string, hexB: string): number {
  const luminance = (hex: string) => {
    const channels = [1, 3, 5]
      .map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
      .map((v) => (v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4)));
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
  };
  const [l1, l2] = [luminance(hexA), luminance(hexB)];
  return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
}

// Mirrors --gradient-brand-text / --brand-text-fallback in app/globals.css.
const LIGHT_TEXT_STOPS = ["#0f766e", "#0891b2", "#6366f1", "#1d4ed8"];
const DARK_TEXT_STOPS = ["#2dd4bf", "#22d3ee", "#a5b4fc", "#93c5fd"];

describe("brand gradient text contrast", () => {
  it("keeps every light-theme stop above the 3:1 large-text floor on white", () => {
    for (const stop of LIGHT_TEXT_STOPS) {
      expect(contrastRatio(stop, "#ffffff")).toBeGreaterThanOrEqual(3);
    }
  });

  it("keeps every dark-theme stop above the 3:1 large-text floor on the app background", () => {
    for (const stop of DARK_TEXT_STOPS) {
      expect(contrastRatio(stop, "#020617")).toBeGreaterThanOrEqual(3);
    }
  });

  it("rejects the decorative stops for text — they are the trap this guards", () => {
    // --brand-cyan and --brand-violet, the mid-stops of --gradient-brand.
    expect(contrastRatio("#22d3ee", "#ffffff")).toBeLessThan(3);
    expect(contrastRatio("#818cf8", "#ffffff")).toBeLessThan(3);
  });
});

describe("LogoMark", () => {
  it("is decorative and exposes no accessible name of its own", () => {
    const { container } = render(<LogoMark />);
    const svg = container.querySelector("svg");
    expect(svg).toHaveAttribute("aria-hidden", "true");
  });

  it("scopes gradient ids per instance so two marks on one page don't collide", () => {
    const { container } = render(
      <>
        <LogoMark idSuffix="header" />
        <LogoMark idSuffix="footer" />
      </>,
    );
    const ids = [...container.querySelectorAll("linearGradient, radialGradient")].map((n) =>
      n.getAttribute("id"),
    );
    expect(new Set(ids).size).toBe(ids.length);
    expect(ids.some((id) => id?.endsWith("-header"))).toBe(true);
    expect(ids.some((id) => id?.endsWith("-footer"))).toBe(true);
  });

  it("renders both arcs and the spark", () => {
    const { container } = render(<LogoMark idSuffix="solo" />);
    // Two stroked arcs plus the filled spark.
    expect(container.querySelectorAll("path").length).toBe(3);
  });
});

describe("Logo", () => {
  it("links home by default with an accessible name", () => {
    render(<Logo />);
    expect(screen.getByRole("link", { name: "Agora Origin home" })).toHaveAttribute("href", "/");
  });

  it("renders a non-interactive mark when href is null", () => {
    render(<Logo href={null} />);
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    expect(screen.getByText("Agora Origin")).toBeInTheDocument();
  });

  it("hides the wordmark in markOnly mode (collapsed sidebar)", () => {
    render(<Logo markOnly href={null} />);
    expect(screen.queryByText("Agora Origin")).not.toBeInTheDocument();
  });
});
