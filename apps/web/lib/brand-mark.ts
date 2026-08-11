/** The Agora Origin mark as a standalone SVG string, for contexts that
 * can't render the `LogoMark` React component: `next/og` `ImageResponse`
 * routes (apple-icon, opengraph-image) rasterize through Satori, which
 * takes an `<img src="data:...">` far more reliably than inline SVG JSX.
 *
 * Colors are literal hex, not `var(--brand-*)`: these images are generated
 * on the server with no document and no CSS custom properties. Geometry
 * matches `components/logo.tsx` — see its comment for why the crescents
 * are filled paths rather than stroked arcs. Keep the two in sync.
 *
 * The browser tab icon deliberately does *not* come from here — that is
 * `app/favicon.ico`, the real authored artwork.
 */
export const BRAND_MARK_SVG = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48" fill="none">
<defs>
<linearGradient id="t" x1="8" y1="12" x2="30" y2="38" gradientUnits="userSpaceOnUse"><stop stop-color="#0d9488"/><stop offset="1" stop-color="#2dd4bf"/></linearGradient>
<linearGradient id="b" x1="40" y1="12" x2="18" y2="38" gradientUnits="userSpaceOnUse"><stop stop-color="#818cf8"/><stop offset="1" stop-color="#1d4ed8"/></linearGradient>
<radialGradient id="s" cx="0.5" cy="0.5" r="0.5"><stop stop-color="#fde68a" stop-opacity="0.7"/><stop offset="1" stop-color="#fbbf24" stop-opacity="0"/></radialGradient>
</defs>
<path d="M25.24 38A15.1 15.1 0 1 0 21.6 12.1L23.39 17.7A9.8 9.8 0 1 1 25.42 32.12Z" fill="url(#b)"/>
<path d="M22.76 10A15.1 15.1 0 1 0 26.4 35.9L24.61 30.3A9.8 9.8 0 1 1 22.58 15.88Z" fill="url(#t)"/>
<circle cx="24" cy="24" r="7" fill="url(#s)"/>
<path d="M24 18.4c.42 3.2 2.18 4.96 5.38 5.38-3.2.42-4.96 2.18-5.38 5.38-.42-3.2-2.18-4.96-5.38-5.38 3.2-.42 4.96-2.18 5.38-5.38Z" fill="#fbbf24"/>
</svg>`;

/** Base64 rather than percent-encoding: the markup contains `#` characters
 * in every color, which terminate a data URI as a fragment if left raw. */
export const BRAND_MARK_DATA_URI = `data:image/svg+xml;base64,${Buffer.from(
  BRAND_MARK_SVG,
).toString("base64")}`;
