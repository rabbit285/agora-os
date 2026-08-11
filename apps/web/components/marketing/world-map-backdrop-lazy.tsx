"use client";

import dynamic from "next/dynamic";

/** Loads the three.js backdrop only in the browser, and only once the rest
 * of the page is interactive.
 *
 * three.js is ~600KB of JavaScript for a decorative graphic — putting it
 * in the initial marketing bundle would make it compete with the content
 * it sits behind. `ssr: false` also keeps it out of the server render,
 * where a WebGL canvas has nothing to draw into anyway.
 *
 * The wrapper exists because `ssr: false` is only permitted from a Client
 * Component, and the marketing pages are server-rendered.
 */
const WorldMapBackdrop = dynamic(
  () => import("@/components/marketing/world-map-backdrop").then((m) => m.WorldMapBackdrop),
  { ssr: false },
);

export function WorldMapBackdropLazy({ className }: { className?: string }) {
  return <WorldMapBackdrop className={className} />;
}
