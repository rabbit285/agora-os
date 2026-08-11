import Image from "next/image";

/** The hero's right-hand visual.
 *
 * Deliberately not framed in a card. The artwork already dissolves to
 * white along its left edge, so a border and shadow would fight it —
 * cutting a hard rectangle through a gradient that was drawn to blend.
 * Instead it bleeds into the page, with a mask carrying the fade around
 * the remaining edges and the hero's own brand glow sitting behind it.
 *
 * Real content, not decoration: it depicts the teams the product is for,
 * so it carries an alt description rather than aria-hidden.
 */
export function HeroVisual() {
  return (
    <div className="relative">
      {/* The same two-lobe brand light the rest of the hero sits in, so the
          artwork looks lit by the page rather than pasted onto it. */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -inset-10 rounded-[3rem] bg-[radial-gradient(58%_58%_at_55%_45%,var(--aurora-blue),transparent_70%)] blur-2xl"
      />

      <div
        className="relative"
        style={{
          // Feathers the top, bottom, and right edges; the left is left
          // alone because the artwork already dissolves to white there.
          //
          // Two linear masks intersected rather than one radial: a radial
          // large enough to keep the middle opaque still leaves the
          // mid-points of each edge nearly solid, so the image ended on a
          // visible straight cut. Intersecting per-axis gradients fades
          // every edge by a known amount instead.
          maskImage:
            "linear-gradient(to bottom, transparent 0%, #000 9%, #000 91%, transparent 100%), linear-gradient(to left, transparent 0%, #000 11%, #000 100%)",
          WebkitMaskImage:
            "linear-gradient(to bottom, transparent 0%, #000 9%, #000 91%, transparent 100%), linear-gradient(to left, transparent 0%, #000 11%, #000 100%)",
          maskComposite: "intersect",
          WebkitMaskComposite: "source-in",
        }}
      >
        <Image
          src="/images/hero-workspace.jpg"
          alt="Teams across compliance, security, sales, and customer support working from shared dashboards"
          width={1669}
          height={943}
          // The hero image is the largest element above the fold, so it is
          // almost certainly the LCP candidate — loaded eagerly with an
          // explicit fetch priority rather than lazily.
          priority
          sizes="(max-width: 1024px) 100vw, 52vw"
          className="h-auto w-full select-none"
        />
      </div>
    </div>
  );
}
