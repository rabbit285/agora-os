"use client";

import { useEffect, useRef } from "react";
import * as THREE from "three";

import { WORLD_MASK_COLS, WORLD_MASK_ROWS, decodeWorldMask } from "@/lib/world-land-mask";
import { cn } from "@/lib/utils";

/** Brand sweep sampled across longitude, so the map is lit by the same
 * teal -> cyan -> indigo -> blue arc the mark draws.
 *
 * These are the *darker* stops (the same ones --gradient-brand-text uses),
 * not the bright decorative ones. The map sits on --bg-app, which is
 * near-white in the light theme, and the bright stops disappeared into it
 * — --brand-cyan is 1.81:1 there. Mid-tones keep the map present on white
 * while staying visible on the dark theme's near-black, which matters
 * because a background canvas can't cheaply re-theme itself. */
const SWEEP = [
  new THREE.Color("#0f766e"),
  new THREE.Color("#0891b2"),
  new THREE.Color("#6366f1"),
  new THREE.Color("#2563eb"),
];

function sweepColor(t: number, out: THREE.Color): THREE.Color {
  const scaled = Math.min(Math.max(t, 0), 1) * (SWEEP.length - 1);
  const i = Math.min(Math.floor(scaled), SWEEP.length - 2);
  return out.copy(SWEEP[i]).lerp(SWEEP[i + 1], scaled - i);
}

/** A soft round sprite. PointsMaterial draws square points by default,
 * which reads as pixel noise at this scale rather than a dot map. */
function createDotTexture(): THREE.Texture {
  const size = 64;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d")!;
  const gradient = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
  gradient.addColorStop(0, "rgba(255,255,255,1)");
  gradient.addColorStop(0.5, "rgba(255,255,255,0.85)");
  gradient.addColorStop(1, "rgba(255,255,255,0)");
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, size, size);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
}

/**
 * A dot-matrix world map behind a marketing section.
 *
 * Purely decorative: `aria-hidden`, non-interactive, and the section reads
 * identically with it absent. It is therefore treated as strictly
 * optional at runtime — no WebGL, a lost context, or reduced-motion all
 * degrade to something still correct rather than to a broken canvas.
 *
 * Deliberately not react-three-fiber: this is one static point cloud with
 * a sine offset, and a reconciler plus its React bindings would be a far
 * larger dependency than the ~150 lines of plain three.js it would save.
 */
export function WorldMapBackdrop({ className }: { className?: string }) {
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true, powerPreference: "low-power" });
    } catch {
      // No WebGL (old browser, blocked, or software rendering disabled).
      // Nothing to unwind and nothing to signal: the container is an empty,
      // transparent, non-interactive box, so leaving it in place looks
      // identical to removing it — and tracking the failure in state just
      // to render null would mean a setState inside this effect.
      return;
    }

    // Capped rather than raw devicePixelRatio: this is a background, and
    // on a 3x phone the extra pixels cost real battery for no visible gain.
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    // The container can still be 0x0 on the first effect pass; sizing off
    // that gives a NaN aspect ratio and a blank canvas that never
    // recovers. Fall back to something sane and let the ResizeObserver
    // below correct it on the first real layout.
    const initialWidth = container.clientWidth || 1;
    const initialHeight = container.clientHeight || 1;
    renderer.setSize(initialWidth, initialHeight, false);
    renderer.domElement.style.width = "100%";
    renderer.domElement.style.height = "100%";
    renderer.domElement.style.display = "block";
    container.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(38, initialWidth / initialHeight, 0.1, 100);
    camera.position.set(0, 1.2, 17.2);
    camera.lookAt(0, 0, 0);

    const cells = decodeWorldMask();
    const positions: number[] = [];
    const colors: number[] = [];
    const phases: number[] = [];
    const color = new THREE.Color();

    const WIDTH = 26;
    const HEIGHT = (WIDTH * WORLD_MASK_ROWS) / WORLD_MASK_COLS;

    for (let row = 0; row < WORLD_MASK_ROWS; row++) {
      for (let col = 0; col < WORLD_MASK_COLS; col++) {
        if (!cells[row * WORLD_MASK_COLS + col]) continue;
        const u = col / (WORLD_MASK_COLS - 1);
        const v = row / (WORLD_MASK_ROWS - 1);
        positions.push((u - 0.5) * WIDTH, (0.5 - v) * HEIGHT, 0);
        sweepColor(u, color);
        colors.push(color.r, color.g, color.b);
        // Per-dot phase so the wave travels rather than pulsing in unison.
        phases.push(u * 6 + v * 3);
      }
    }

    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
    geometry.setAttribute("color", new THREE.Float32BufferAttribute(colors, 3));

    const dotTexture = createDotTexture();
    const material = new THREE.PointsMaterial({
      size: 0.17,
      map: dotTexture,
      vertexColors: true,
      transparent: true,
      opacity: 0.85,
      depthWrite: false,
      sizeAttenuation: true,
    });

    const points = new THREE.Points(geometry, material);
    // Barely tilted: enough that the dots gain depth as the wave moves
    // through them, but not so much that the continents skew and stop
    // reading as a map.
    points.rotation.x = -0.16;
    scene.add(points);

    const positionAttribute = geometry.getAttribute("position") as THREE.BufferAttribute;

    function renderFrame(elapsed: number) {
      const array = positionAttribute.array as Float32Array;
      for (let i = 0, p = 0; i < array.length; i += 3, p++) {
        array[i + 2] = Math.sin(elapsed * 0.55 + phases[p]) * 0.42;
      }
      positionAttribute.needsUpdate = true;
      renderer.render(scene, camera);
    }

    // Reduced motion still gets the map — just held still. Removing it
    // entirely would change the section's composition for those users.
    if (reducedMotion) {
      renderFrame(0);
    }

    let frame = 0;
    let running = false;
    let elapsed = 0;
    const clock = new THREE.Clock();

    function loop() {
      frame = requestAnimationFrame(loop);
      // Accumulated from clamped deltas rather than read from the clock:
      // the loop is paused whenever the section scrolls off screen or the
      // tab is hidden, and both a reset clock and a raw delta across that
      // gap make the wave jump on resume. Clamping caps any single step at
      // roughly two frames' worth.
      elapsed += Math.min(clock.getDelta(), 0.05);
      renderFrame(elapsed);
    }

    function start() {
      if (running || reducedMotion) return;
      running = true;
      clock.getDelta(); // discard the idle gap
      loop();
    }

    function stop() {
      if (!running) return;
      running = false;
      cancelAnimationFrame(frame);
    }

    // Only animate while actually on screen — a marketing page is mostly
    // scrolled past this section, and a rAF loop running the whole time
    // would burn a core for nothing.
    let onScreen = false;
    const observer = new IntersectionObserver(
      ([entry]) => {
        onScreen = entry.isIntersecting;
        if (onScreen && !document.hidden) start();
        else stop();
      },
      { threshold: 0 },
    );
    observer.observe(container);

    // Tracked explicitly rather than re-queried from the observer on
    // resume: IntersectionObserver only reports *changes*, so there is no
    // way to ask it whether the element is on screen right now, and
    // resuming blind would restart the loop for a section the reader has
    // long since scrolled past.
    function onVisibilityChange() {
      if (document.hidden) stop();
      else if (onScreen) start();
    }
    document.addEventListener("visibilitychange", onVisibilityChange);

    const resizeObserver = new ResizeObserver(() => {
      const { clientWidth, clientHeight } = container;
      if (clientWidth === 0 || clientHeight === 0) return;
      camera.aspect = clientWidth / clientHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(clientWidth, clientHeight, false);
      if (reducedMotion) renderFrame(0);
    });
    resizeObserver.observe(container);

    function onContextLost(event: Event) {
      event.preventDefault();
      stop();
    }
    renderer.domElement.addEventListener("webglcontextlost", onContextLost);

    return () => {
      stop();
      observer.disconnect();
      resizeObserver.disconnect();
      document.removeEventListener("visibilitychange", onVisibilityChange);
      renderer.domElement.removeEventListener("webglcontextlost", onContextLost);
      // three.js holds GPU resources that garbage collection can't reach.
      geometry.dispose();
      material.dispose();
      dotTexture.dispose();
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, []);

  return (
    <div
      ref={containerRef}
      aria-hidden="true"
      className={cn("pointer-events-none absolute inset-0 select-none", className)}
    />
  );
}
