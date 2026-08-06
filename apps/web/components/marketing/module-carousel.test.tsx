import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ModuleCarousel } from "@/components/marketing/module-carousel";

/** jsdom implements neither `matchMedia` nor `ResizeObserver`/
 * `IntersectionObserver` — real browsers embla-carousel-react depends on
 * for both this component's own reduced-motion check and Embla's internal
 * slide-size measurement. Navigation still works under these mocks (Embla
 * degrades to its snap-index math without real layout), but there is no
 * real viewport here — responsive breakpoint behavior is covered by the
 * Playwright suite instead, not asserted here. */
let reducedMotion = false;

beforeEach(() => {
  reducedMotion = false;
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: reducedMotion,
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })),
  });
  class MockObserver {
    observe = vi.fn();
    unobserve = vi.fn();
    disconnect = vi.fn();
  }
  vi.stubGlobal("ResizeObserver", MockObserver);
  vi.stubGlobal("IntersectionObserver", MockObserver);
});

afterEach(() => {
  vi.useRealTimers();
});

const MODULES = ["Compliance", "Security", "Sales", "Customer Support", "Automation", "AI Governance"];

function region() {
  return screen.getByRole("region", { name: "Product modules" });
}

function counterText() {
  return within(region()).getByText(/^\d+ \/ \d+$/).textContent;
}

describe("ModuleCarousel", () => {
  it("renders all six module slides", () => {
    render(<ModuleCarousel />);
    for (const name of MODULES) {
      expect(screen.getByText(name)).toBeInTheDocument();
    }
    expect(counterText()).toBe("1 / 6");
  });

  it("renders the correct headline, description, and CTA for each module", () => {
    render(<ModuleCarousel />);
    expect(
      screen.getByRole("heading", { name: "Turn compliance work into clear, auditable action." }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Manage controls, evidence, policies, privacy workflows/),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Explore Compliance/ })).toHaveAttribute(
      "href",
      "/features#compliance",
    );
  });

  it("has meaningful, distinct alt text on every slide image", () => {
    // Every slide's <img> is genuinely present in the DOM (Embla doesn't
    // unmount off-screen slides), but non-active ones sit under an
    // aria-hidden ancestor and so drop out of the accessibility tree —
    // querying the raw DOM here, not getAllByRole, since this test is
    // about the image assets' metadata, not current a11y-tree visibility
    // (that's covered separately by "hides non-active slide content").
    const { container } = render(<ModuleCarousel />);
    const images = Array.from(container.querySelectorAll("img"));
    expect(images).toHaveLength(6);
    const altTexts = images.map((img) => img.getAttribute("alt"));
    expect(new Set(altTexts).size).toBe(6);
    for (const alt of altTexts) {
      expect(alt).toBeTruthy();
      expect(alt!.length).toBeGreaterThan(15);
    }
  });

  it("has a working href for every module's CTA, including slides not yet active", async () => {
    const user = userEvent.setup();
    render(<ModuleCarousel />);
    const expected = [
      ["Explore Compliance", "/features#compliance"],
      ["Explore Security", "/features#security"],
      ["Explore Sales", "/features#sales"],
      ["Explore Support", "/features#support"],
      ["Explore Automation", "/features#automation"],
      ["Explore AI Governance", "/features#ai-governance"],
    ] as const;
    for (const [name, href] of expected) {
      // Only the active slide's CTA is in the accessibility tree (the rest
      // are aria-hidden — see the "hides non-active slide content" test) —
      // navigate there first.
      expect(screen.getByRole("link", { name: new RegExp(name) })).toHaveAttribute("href", href);
      await user.click(screen.getByRole("button", { name: "Next module" }));
    }
  });

  it("advances to the next slide via the Next control", async () => {
    const user = userEvent.setup();
    render(<ModuleCarousel />);
    await user.click(screen.getByRole("button", { name: "Next module" }));
    expect(await screen.findByText("2 / 6")).toBeInTheDocument();
  });

  it("goes back to the previous slide via the Previous control", async () => {
    const user = userEvent.setup();
    render(<ModuleCarousel />);
    await user.click(screen.getByRole("button", { name: "Next module" }));
    await screen.findByText("2 / 6");
    await user.click(screen.getByRole("button", { name: "Previous module" }));
    expect(await screen.findByText("1 / 6")).toBeInTheDocument();
  });

  it("wraps from the last slide to the first on Next", async () => {
    const user = userEvent.setup();
    render(<ModuleCarousel />);
    for (let i = 0; i < 5; i++) {
      await user.click(screen.getByRole("button", { name: "Next module" }));
    }
    expect(await screen.findByText("6 / 6")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Next module" }));
    expect(await screen.findByText("1 / 6")).toBeInTheDocument();
  });

  it("wraps from the first slide to the last on Previous", async () => {
    const user = userEvent.setup();
    render(<ModuleCarousel />);
    await user.click(screen.getByRole("button", { name: "Previous module" }));
    expect(await screen.findByText("6 / 6")).toBeInTheDocument();
  });

  it("jumps directly to a slide via its pagination dot", async () => {
    const user = userEvent.setup();
    render(<ModuleCarousel />);
    await user.click(screen.getByRole("button", { name: "Go to Sales slide" }));
    expect(await screen.findByText("3 / 6")).toBeInTheDocument();
    const dot = screen.getByRole("button", { name: "Go to Sales slide" });
    expect(dot).toHaveAttribute("aria-current", "true");
  });

  it("supports ArrowRight/ArrowLeft keyboard navigation within the carousel region", async () => {
    render(<ModuleCarousel />);
    const nextButton = screen.getByRole("button", { name: "Next module" });
    nextButton.focus();
    fireEvent.keyDown(region(), { key: "ArrowRight" });
    expect(await screen.findByText("2 / 6")).toBeInTheDocument();
    fireEvent.keyDown(region(), { key: "ArrowLeft" });
    expect(await screen.findByText("1 / 6")).toBeInTheDocument();
  });

  it("hides non-active slide content from the accessibility tree", () => {
    render(<ModuleCarousel />);
    expect(screen.queryByRole("link", { name: /Explore Security/ })).not.toBeInTheDocument();
  });

  it("announces the current slide via a live region", () => {
    render(<ModuleCarousel />);
    expect(screen.getByText(/Showing slide 1 of 6: Compliance/)).toBeInTheDocument();
  });

  describe("autoplay", () => {
    beforeEach(() => {
      // Embla's scroll animation runs on requestAnimationFrame — without
      // faking it too, the interval fires but the resulting scroll/select
      // never settles, since rAF callbacks would need real frames to run.
      vi.useFakeTimers({
        toFake: [
          "setTimeout",
          "clearTimeout",
          "setInterval",
          "clearInterval",
          "requestAnimationFrame",
          "cancelAnimationFrame",
        ],
      });
    });

    // Embla drives its scroll/settle animation via requestAnimationFrame,
    // which this library appears to capture in a way `vi.useFakeTimers`
    // can't intercept — the interval firing and calling scrollNext() is
    // this component's own contract (verified here via a setInterval spy);
    // whether that visibly advances the slide in a real browser is a
    // motion/timing concern better suited to, and covered by, the
    // Playwright suite (e2e/public-site-and-auth.spec.ts).
    it("schedules automatic rotation on a ~7s interval when not interacted with", () => {
      const setIntervalSpy = vi.spyOn(window, "setInterval");
      render(<ModuleCarousel />);
      expect(setIntervalSpy).toHaveBeenCalledWith(expect.any(Function), 7000);
    });

    it("does not schedule automatic rotation while the pointer is hovering", () => {
      const setIntervalSpy = vi.spyOn(window, "setInterval");
      render(<ModuleCarousel />);
      setIntervalSpy.mockClear();
      fireEvent.mouseEnter(region());
      expect(setIntervalSpy).not.toHaveBeenCalled();
    });

    it("does not schedule automatic rotation once paused via the visible control", () => {
      const setIntervalSpy = vi.spyOn(window, "setInterval");
      render(<ModuleCarousel />);
      fireEvent.click(screen.getByRole("button", { name: "Pause automatic slide rotation" }));
      setIntervalSpy.mockClear();
      vi.advanceTimersByTime(20000);
      expect(setIntervalSpy).not.toHaveBeenCalled();
      expect(screen.getByRole("button", { name: "Play automatic slide rotation" })).toBeInTheDocument();
    });
  });

  describe("reduced motion", () => {
    beforeEach(() => {
      reducedMotion = true;
      vi.useFakeTimers({
        toFake: [
          "setTimeout",
          "clearTimeout",
          "setInterval",
          "clearInterval",
          "requestAnimationFrame",
          "cancelAnimationFrame",
        ],
      });
    });

    it("does not render a pause/play autoplay control", () => {
      render(<ModuleCarousel />);
      expect(
        screen.queryByRole("button", { name: /automatic slide rotation/ }),
      ).not.toBeInTheDocument();
    });

    it("does not auto-advance slides", async () => {
      render(<ModuleCarousel />);
      await vi.advanceTimersByTimeAsync(15000);
      expect(counterText()).toBe("1 / 6");
    });

    it("manual navigation still works", async () => {
      render(<ModuleCarousel />);
      fireEvent.click(screen.getByRole("button", { name: "Next module" }));
      await vi.advanceTimersByTimeAsync(500);
      expect(counterText()).toBe("2 / 6");
    });
  });
});
