import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { CardActionArrow, CardMedia, InteractiveCard } from "@/components/marketing/interactive-card";

describe("InteractiveCard", () => {
  it("renders a real <a> when given an href, not a clickable <div>", () => {
    render(<InteractiveCard href="/features#compliance">Compliance</InteractiveCard>);
    const link = screen.getByRole("link", { name: "Compliance" });
    expect(link).toHaveAttribute("href", "/features#compliance");
  });

  it("renders a real <button> when given onClick, not a clickable <div>", async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    render(<InteractiveCard onClick={onClick}>Select me</InteractiveCard>);
    const button = screen.getByRole("button", { name: "Select me" });
    expect(button).toHaveAttribute("type", "button");
    await user.click(button);
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("activates via Enter and Space when it is a button", async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    render(<InteractiveCard onClick={onClick}>Select me</InteractiveCard>);
    const button = screen.getByRole("button", { name: "Select me" });
    button.focus();
    await user.keyboard("{Enter}");
    expect(onClick).toHaveBeenCalledTimes(1);
    await user.keyboard(" ");
    expect(onClick).toHaveBeenCalledTimes(2);
  });

  it("renders a plain, non-interactive <div> when given neither href nor onClick", () => {
    const { container } = render(<InteractiveCard>Just a card</InteractiveCard>);
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    const card = container.querySelector("div.group");
    expect(card).toBeInTheDocument();
    expect(card).not.toHaveAttribute("tabindex");
  });

  it("applies the persistent selected treatment regardless of hover", () => {
    render(
      <InteractiveCard href="/pricing" selected>
        Featured plan
      </InteractiveCard>,
    );
    const link = screen.getByRole("link", { name: "Featured plan" });
    expect(link.className).toContain("border-[var(--card-glow)]");
    expect(link.className).toContain("shadow-[var(--shadow-token-glow)]");
  });

  it("uses the default (unselected) border/shadow when not selected, not the persistent selected treatment", () => {
    render(<InteractiveCard href="/pricing">Regular plan</InteractiveCard>);
    const link = screen.getByRole("link", { name: "Regular plan" });
    // hover:/focus-visible: variants of the card-glow border are expected
    // (that's the hover feedback) — only the *unconditional*
    // border-[var(--card-glow)] (the selected/persistent state) is
    // asserted absent here.
    expect(link.className).toContain("border-[var(--border-default)]");
    expect(link.className.split(" ")).not.toContain("border-[var(--card-glow)]");
  });

  it("renders a disabled card as inert, with no href/onClick behavior", () => {
    const onClick = vi.fn();
    render(
      <InteractiveCard onClick={onClick} disabled>
        Disabled
      </InteractiveCard>,
    );
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    const card = screen.getByText("Disabled");
    expect(card.closest("[aria-disabled]")).toHaveAttribute("aria-disabled", "true");
  });

  it("includes hover/focus-visible scale classes for a real link card, with a motion-reduce override", () => {
    render(<InteractiveCard href="/pricing">Card</InteractiveCard>);
    const link = screen.getByRole("link", { name: "Card" });
    expect(link.className).toContain("hover:scale-[1.02]");
    expect(link.className).toContain("focus-visible:scale-[1.02]");
    expect(link.className).toContain("motion-reduce:hover:scale-100");
  });

  it("uses passive hover/focus-within styling (no scale) for a static card with a nested control", () => {
    render(
      <InteractiveCard>
        <button type="button">Nested CTA</button>
      </InteractiveCard>,
    );
    const outer = screen.getByText("Nested CTA").closest("div.group");
    expect(outer!.className).toContain("focus-within:shadow-[var(--shadow-token-glow)]");
    expect(outer!.className).not.toContain("hover:scale-[1.02]");
  });
});

describe("CardMedia", () => {
  it("wraps its children in a group-hover-reactive, overflow-hidden container", () => {
    const { container } = render(
      <CardMedia className="aspect-video">
        {/* eslint-disable-next-line @next/next/no-img-element -- a plain <img> is enough to verify CardMedia's wrapper, no real page renders this */}
        <img src="/x.jpg" alt="x" />
      </CardMedia>
    );
    const outer = container.firstElementChild as HTMLElement;
    expect(outer.className).toContain("overflow-hidden");
    const inner = outer.firstElementChild as HTMLElement;
    expect(inner.className).toContain("group-hover:scale-[1.05]");
    expect(inner.className).toContain("motion-reduce:group-hover:scale-100");
  });
});

describe("CardActionArrow", () => {
  it("renders a decorative, group-hover-reactive arrow", () => {
    const { container } = render(<CardActionArrow />);
    const svg = container.querySelector("svg");
    expect(svg).toHaveAttribute("aria-hidden", "true");
    expect(svg!.getAttribute("class")).toContain("group-hover:translate-x-1");
  });
});
