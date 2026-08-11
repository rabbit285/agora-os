import { ImageResponse } from "next/og";

import { BRAND_MARK_DATA_URI } from "@/lib/brand-mark";

export const size = { width: 180, height: 180 };
export const contentType = "image/png";

/** iOS home-screen icon. Kept as a generated PNG rather than deferring to
 * `app/favicon.ico`, because iOS ignores .ico entirely and falls back to a
 * screenshot of the page without this. On a dark ground, matching the
 * app's own nav chrome — the mark's arcs are drawn to glow against dark. */
export default function AppleIcon() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "#0b1220",
        }}
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={BRAND_MARK_DATA_URI} width={136} height={136} alt="" />
      </div>
    ),
    { ...size },
  );
}
