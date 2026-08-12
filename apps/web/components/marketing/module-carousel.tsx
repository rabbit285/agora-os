"use client";

import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";
import Image from "next/image";
import Link from "next/link";
import useEmblaCarousel from "embla-carousel-react";
import { ChevronLeft, ChevronRight, Pause, Play } from "lucide-react";

import { CardActionArrow, CardMedia, InteractiveCard } from "@/components/marketing/interactive-card";
import { SectionHeader } from "@/components/marketing/section-header";
import { cn } from "@/lib/utils";

type Slide = {
  id: string;
  label: string;
  headline: string;
  description: string;
  cta: string;
  href: string;
  image: string;
  alt: string;
};

const SLIDES: Slide[] = [
  {
    id: "compliance",
    label: "Compliance",
    headline: "Turn compliance work into clear, auditable action.",
    description:
      "Manage controls, evidence, policies, privacy workflows, risks, vendors, and audits from one governed workspace.",
    cta: "Explore Compliance",
    href: "/features#compliance",
    image: "/images/modules/module-compliance.jpg",
    alt: "Business team in a glass-walled conference room reviewing a compliance readiness dashboard on a large screen.",
  },
  {
    id: "security",
    label: "Security",
    headline: "Detect threats early and respond with confidence.",
    description:
      "Connect assets, findings, alerts, incidents, remediation, and compliance escalation through one operational view.",
    cta: "Explore Security",
    href: "/features#security",
    image: "/images/modules/module-security.jpg",
    alt: "Security team monitoring global threat data across a wall of screens in a security operations center.",
  },
  {
    id: "sales",
    label: "Sales",
    headline: "Find the right companies and buyers faster.",
    description:
      "Search companies and decision-makers, evaluate ICP fit, research prospects, and move approved opportunities into outreach.",
    cta: "Explore Sales",
    href: "/features#sales",
    image: "/images/modules/module-sales.jpg",
    alt: "Sales team reviewing pipeline and performance charts on a conference room screen.",
  },
  {
    id: "support",
    label: "Customer Support",
    headline: "Deliver support that stays fast, personal, and smart.",
    description:
      "Give agents customer context, AI-assisted summaries, suggested responses, SLA visibility, and governed escalation tools.",
    cta: "Explore Support",
    href: "/features#support",
    image: "/images/modules/module-support.jpg",
    alt: "Customer support agents wearing headsets and assisting customers from their laptops.",
  },
  {
    id: "automation",
    label: "Automation",
    headline: "Automate critical work without losing control.",
    description:
      "Build workflows with triggers, decisions, approvals, AI actions, integrations, retries, and complete execution history.",
    cta: "Explore Automation",
    href: "/features#automation",
    image: "/images/modules/module-automation.jpg",
    alt: "Team reviewing a connected automated-workflow diagram on a large screen.",
  },
  {
    id: "ai-governance",
    label: "AI Governance",
    headline: "Govern AI systems with visibility, review, and trust.",
    description:
      "Maintain an AI system inventory, assess risk, manage incidents, collect evidence, and keep important actions reviewable.",
    cta: "Explore AI Governance",
    href: "/features#ai-governance",
    image: "/images/modules/module-ai-governance.jpg",
    alt: "Two colleagues reviewing a printed governance document together at a desk.",
  },
];

const AUTOPLAY_INTERVAL_MS = 7000;

function subscribeToReducedMotionPreference(onChange: () => void) {
  const query = window.matchMedia("(prefers-reduced-motion: reduce)");
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}

function getReducedMotionPreference() {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

// No window on the server — assume motion is fine until the client
// snapshot resolves, matching the global CSS reduced-motion rule's own
// scope (it only ever applies client-side anyway).
function getReducedMotionPreferenceServerSnapshot() {
  return false;
}

export function ModuleCarousel() {
  const [emblaRef, emblaApi] = useEmblaCarousel({
    loop: true,
    align: "center",
    skipSnaps: false,
    // Without this, Embla's own pointerdown handling (which fires on the
    // viewport ancestor before React's delegated onClick even runs) calls
    // preventDefault() on every click that starts inside a slide — including
    // the CTA link — so Next's <Link> sees defaultPrevented and silently
    // skips navigation. Telling Embla to skip drag-engagement when the
    // gesture starts on an <a>/<button> lets those clicks through untouched.
    watchDrag: (_, event) => {
      const target = event.target as HTMLElement;
      return !target.closest("a, button");
    },
  });
  const [selectedIndex, setSelectedIndex] = useState(0);
  const prefersReducedMotion = useSyncExternalStore(
    subscribeToReducedMotionPreference,
    getReducedMotionPreference,
    getReducedMotionPreferenceServerSnapshot,
  );
  const [isPaused, setIsPaused] = useState(false);
  const [isInteracting, setIsInteracting] = useState(false);
  const autoplayTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  const scrollPrev = useCallback(() => emblaApi?.scrollPrev(), [emblaApi]);
  const scrollNext = useCallback(() => emblaApi?.scrollNext(), [emblaApi]);
  const scrollTo = useCallback((index: number) => emblaApi?.scrollTo(index), [emblaApi]);

  useEffect(() => {
    if (!emblaApi) return;
    const onSelect = () => setSelectedIndex(emblaApi.selectedScrollSnap());
    onSelect();
    emblaApi.on("select", onSelect);
    emblaApi.on("reInit", onSelect);
    return () => {
      emblaApi.off("select", onSelect);
      emblaApi.off("reInit", onSelect);
    };
  }, [emblaApi]);

  const autoplayActive = !prefersReducedMotion && !isPaused && !isInteracting;

  useEffect(() => {
    if (!emblaApi || !autoplayActive) return;
    autoplayTimer.current = setInterval(() => {
      emblaApi.scrollNext();
    }, AUTOPLAY_INTERVAL_MS);
    return () => {
      if (autoplayTimer.current) clearInterval(autoplayTimer.current);
    };
  }, [emblaApi, autoplayActive]);

  const total = SLIDES.length;
  const current = SLIDES[selectedIndex] ?? SLIDES[0];

  return (
    <section className="py-20">
      {/* The heading stays in the normal content column; only the carousel
          breaks out. A full-width band of prose would be unreadable. */}
      <div className="mx-auto max-w-[var(--content-max-width)] px-4 sm:px-6 lg:px-8">
        <SectionHeader
          eyebrow="Platform"
          title="One platform for the work that keeps your business moving."
          description="Bring compliance, security, sales, customer support, automation, and AI governance into one connected workspace."
        />
      </div>

      <div
        role="region"
        aria-roledescription="carousel"
        aria-label="Product modules"
        // Wider than --content-max-width on purpose: the neighbouring
        // slides are meant to run off both edges, which is what signals
        // "there is more here" without a caption saying so. Capped at
        // 120rem so an ultrawide monitor doesn't get an absurd slide.
        className="mx-auto mt-12 max-w-[120rem] px-4 sm:px-6 lg:px-0"
        onMouseEnter={() => setIsInteracting(true)}
        onMouseLeave={() => setIsInteracting(false)}
        onFocus={() => setIsInteracting(true)}
        onBlur={(event) => {
          if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
            setIsInteracting(false);
          }
        }}
        onKeyDown={(event) => {
          if (event.key === "ArrowLeft") {
            event.preventDefault();
            scrollPrev();
          } else if (event.key === "ArrowRight") {
            event.preventDefault();
            scrollNext();
          }
        }}
      >
        {/* The viewport must clip horizontally — that is what makes the
            neighbouring slides run off the edges. But it clips vertically
            too, which sheared the active slide's bloom flat against the
            top and bottom of the card. Padding opens up room inside the
            clip for the glow to finish; the matching negative margin
            takes that space back out of the layout, so nothing moves. */}
        <div className="overflow-hidden py-12 -my-12" ref={emblaRef}>
          <div className="-mx-2 flex sm:-mx-3 lg:-mx-4">
            {SLIDES.map((slide, index) => {
              const isActive = index === selectedIndex;
              const media = (
                <>
                  <CardMedia className="absolute inset-0">
                    <Image
                      src={slide.image}
                      alt={slide.alt}
                      fill
                      sizes="(max-width: 640px) 100vw, (max-width: 1024px) 84vw, 68vw"
                      className="object-cover object-[68%_center]"
                      priority={index === 0}
                    />
                  </CardMedia>
                  <div
                    className="pointer-events-none absolute inset-0"
                    style={{
                      background:
                        "linear-gradient(0deg, rgba(15,23,42,0.85) 0%, rgba(15,23,42,0.45) 32%, rgba(15,23,42,0.05) 58%, rgba(15,23,42,0) 75%)",
                    }}
                  />

                  <span className="absolute left-4 top-4 inline-flex items-center rounded-full bg-white/95 px-3 py-1 text-xs font-semibold text-[var(--fg-default)] sm:left-6 sm:top-6 lg:left-10 lg:top-10 lg:px-3.5 lg:py-1.5 lg:text-sm">
                    {slide.label}
                  </span>

                  {/* Copy scales with the card — at the large size the old
                      text held its original scale and read as a caption
                      floating in a lot of empty image. */}
                  <div className="absolute inset-x-4 bottom-4 sm:inset-x-6 sm:bottom-6 lg:inset-x-10 lg:bottom-10 lg:max-w-xl">
                    <h3 className="text-base font-semibold text-white transition-colors duration-[var(--transition-card)] ease-[var(--ease-card)] group-hover:text-white sm:text-lg lg:text-[length:var(--text-3xl)] lg:leading-tight">
                      {slide.headline}
                    </h3>
                    <p className="mt-2 text-xs leading-relaxed text-white/85 sm:text-sm lg:mt-3 lg:text-base">
                      {slide.description}
                    </p>
                    {isActive ? (
                      <Link
                        href={slide.href}
                        className="mt-4 inline-flex items-center gap-1.5 text-sm font-semibold text-white underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--gray-900)]"
                      >
                        {slide.cta}
                        <CardActionArrow className="text-white" />
                      </Link>
                    ) : (
                      <span className="mt-4 inline-flex items-center gap-1.5 text-sm font-semibold text-white/70">
                        {slide.cta}
                        <CardActionArrow className="text-white/70" />
                      </span>
                    )}
                  </div>
                </>
              );

              // Widens rather than just scaling up: at ~68% of a 1900px
              // viewport a 16/9 card would stand 727px tall and push the
              // controls off the fold, so the large breakpoint trades
              // height for width.
              const cardClassName = cn(
                "block aspect-[3/4] w-full overflow-hidden p-0 text-left sm:aspect-[16/9] lg:aspect-[2/1]",
                !isActive &&
                  "scale-[0.95] opacity-[0.85] motion-reduce:scale-100 motion-reduce:opacity-100",
              );

              return (
                <div
                  key={slide.id}
                  className="min-w-0 flex-[0_0_100%] px-2 sm:flex-[0_0_84%] sm:px-3 lg:flex-[0_0_68%] lg:px-4"
                  aria-roledescription="slide"
                  aria-label={`${index + 1} of ${total}: ${slide.label}`}
                  aria-hidden={!isActive}
                >
                  {/* A *named* group: InteractiveCard already claims the
                      bare `group` for its own hover affordances, and an
                      unnamed nested one would make `group-hover` here
                      ambiguous. The bloom is an earlier sibling than the
                      card, so `peer-*` cannot reach it — it only works
                      forwards — which is why the hover is read from the
                      shared wrapper instead. */}
                  <div className="group/slide relative">
                    {/* Always rendered, toggled by opacity, so the light
                        fades in and out instead of popping. */}
                    <div
                      aria-hidden="true"
                      className={cn(
                        "card-bloom pointer-events-none absolute inset-0 rounded-[var(--radius-lg)] transition-opacity duration-[var(--transition-card)] ease-[var(--ease-card)]",
                        "group-hover/slide:opacity-100 group-focus-within/slide:opacity-100",
                        isActive ? "opacity-100" : "opacity-0",
                      )}
                    />
                    {isActive ? (
                      <InteractiveCard selected className={cardClassName}>
                        {media}
                      </InteractiveCard>
                    ) : (
                      <InteractiveCard
                        onClick={() => scrollTo(index)}
                        tabIndex={-1}
                        aria-label={`Show the ${slide.label} module`}
                        className={cardClassName}
                      >
                        {media}
                      </InteractiveCard>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        <div className="mt-6 flex items-center justify-center gap-4">
          <button
            type="button"
            onClick={scrollPrev}
            aria-label="Previous module"
            className="btn-glow flex h-9 w-9 items-center justify-center rounded-full border border-[var(--border-strong)] text-[var(--fg-default)] transition-colors hover:bg-[var(--bg-surface-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--border-focus)]"
          >
            <ChevronLeft className="h-4 w-4" aria-hidden="true" />
          </button>

          <div aria-hidden="true" className="text-sm font-medium tabular-nums text-[var(--fg-muted)]">
            {selectedIndex + 1} / {total}
          </div>

          <div className="flex items-center gap-2">
            {SLIDES.map((slide, index) => (
              <button
                key={slide.id}
                type="button"
                onClick={() => scrollTo(index)}
                aria-label={`Go to ${slide.label} slide`}
                aria-current={index === selectedIndex}
                className={cn(
                  "h-2 rounded-full transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--border-focus)]",
                  index === selectedIndex
                    ? "w-6 bg-[var(--brand-primary)]"
                    : "w-2 bg-[var(--border-strong)] hover:bg-[var(--fg-subtle)]",
                )}
              />
            ))}
          </div>

          <button
            type="button"
            onClick={scrollNext}
            aria-label="Next module"
            className="btn-glow flex h-9 w-9 items-center justify-center rounded-full border border-[var(--border-strong)] text-[var(--fg-default)] transition-colors hover:bg-[var(--bg-surface-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--border-focus)]"
          >
            <ChevronRight className="h-4 w-4" aria-hidden="true" />
          </button>

          {!prefersReducedMotion && (
            <button
              type="button"
              onClick={() => setIsPaused((value) => !value)}
              aria-label={isPaused ? "Play automatic slide rotation" : "Pause automatic slide rotation"}
              aria-pressed={isPaused}
              className="btn-glow flex h-9 w-9 items-center justify-center rounded-full border border-[var(--border-strong)] text-[var(--fg-default)] transition-colors hover:bg-[var(--bg-surface-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--border-focus)]"
            >
              {isPaused ? (
                <Play className="h-4 w-4" aria-hidden="true" />
              ) : (
                <Pause className="h-4 w-4" aria-hidden="true" />
              )}
            </button>
          )}
        </div>

        <div aria-live="polite" className="sr-only">
          Showing slide {selectedIndex + 1} of {total}: {current.label}
        </div>
      </div>
    </section>
  );
}
