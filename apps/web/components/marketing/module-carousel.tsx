"use client";

import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";
import Image from "next/image";
import Link from "next/link";
import useEmblaCarousel from "embla-carousel-react";
import { ArrowRight, ChevronLeft, ChevronRight, Pause, Play } from "lucide-react";

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
    <section className="mx-auto max-w-[var(--content-max-width)] px-4 py-20 sm:px-6 lg:px-8">
      <SectionHeader
        eyebrow="Platform"
        title="One platform for the work that keeps your business moving."
        description="Bring compliance, security, sales, customer support, automation, and AI governance into one connected workspace."
      />

      <div
        role="region"
        aria-roledescription="carousel"
        aria-label="Product modules"
        className="mt-12"
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
        <div className="overflow-hidden" ref={emblaRef}>
          <div className="-mx-2 flex sm:-mx-3">
            {SLIDES.map((slide, index) => {
              const isActive = index === selectedIndex;
              return (
                <div
                  key={slide.id}
                  className="min-w-0 flex-[0_0_100%] px-2 sm:flex-[0_0_84%] sm:px-3 lg:flex-[0_0_68%]"
                  aria-roledescription="slide"
                  aria-label={`${index + 1} of ${total}: ${slide.label}`}
                  aria-hidden={!isActive}
                >
                  <div
                    className={cn(
                      "relative aspect-[3/4] w-full overflow-hidden rounded-[var(--radius-lg)] shadow-[var(--shadow-token-md)] transition-opacity duration-300 sm:aspect-[16/9]",
                      isActive ? "opacity-100" : "opacity-60",
                    )}
                  >
                    <Image
                      src={slide.image}
                      alt={slide.alt}
                      fill
                      sizes="(max-width: 640px) 100vw, (max-width: 1024px) 84vw, 60vw"
                      className="object-cover object-[68%_center]"
                      priority={index === 0}
                    />
                    <div
                      className="pointer-events-none absolute inset-0"
                      style={{
                        background:
                          "linear-gradient(0deg, rgba(15,23,42,0.85) 0%, rgba(15,23,42,0.45) 32%, rgba(15,23,42,0.05) 58%, rgba(15,23,42,0) 75%)",
                      }}
                    />

                    <span className="absolute left-4 top-4 inline-flex items-center rounded-full bg-white/95 px-3 py-1 text-xs font-semibold text-[var(--fg-default)] sm:left-6 sm:top-6">
                      {slide.label}
                    </span>

                    <div className="absolute inset-x-4 bottom-4 sm:inset-x-6 sm:bottom-6 lg:max-w-md">
                      <h3 className="text-base font-semibold text-white sm:text-lg lg:text-xl">{slide.headline}</h3>
                      <p className="mt-2 text-xs leading-relaxed text-white/85 sm:text-sm">{slide.description}</p>
                      <Link
                        href={slide.href}
                        tabIndex={isActive ? 0 : -1}
                        className="mt-4 inline-flex items-center gap-1.5 text-sm font-semibold text-white underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--gray-900)]"
                      >
                        {slide.cta}
                        <ArrowRight className="h-4 w-4" aria-hidden="true" />
                      </Link>
                    </div>
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
            className="flex h-9 w-9 items-center justify-center rounded-full border border-[var(--border-strong)] text-[var(--fg-default)] transition-colors hover:bg-[var(--bg-surface-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--border-focus)]"
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
            className="flex h-9 w-9 items-center justify-center rounded-full border border-[var(--border-strong)] text-[var(--fg-default)] transition-colors hover:bg-[var(--bg-surface-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--border-focus)]"
          >
            <ChevronRight className="h-4 w-4" aria-hidden="true" />
          </button>

          {!prefersReducedMotion && (
            <button
              type="button"
              onClick={() => setIsPaused((value) => !value)}
              aria-label={isPaused ? "Play automatic slide rotation" : "Pause automatic slide rotation"}
              aria-pressed={isPaused}
              className="flex h-9 w-9 items-center justify-center rounded-full border border-[var(--border-strong)] text-[var(--fg-default)] transition-colors hover:bg-[var(--bg-surface-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--border-focus)]"
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
