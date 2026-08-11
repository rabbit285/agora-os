import { ImageResponse } from "next/og";

import { BRAND_MARK_DATA_URI } from "@/lib/brand-mark";

export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

/** The social share card. Dark, matching the app's nav chrome and the
 * closing panel on the marketing site — the mark reads strongest against
 * dark, and a share card competing in a light feed benefits from it. */
export default function OpengraphImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          alignItems: "flex-start",
          justifyContent: "center",
          padding: "80px",
          background: "#0b1220",
          fontFamily: "sans-serif",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 18, marginBottom: 44 }}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={BRAND_MARK_DATA_URI} width={64} height={64} alt="" />
          <div style={{ fontSize: 36, fontWeight: 700, color: "#e8edf7" }}>Agora Origin</div>
        </div>
        <div
          style={{
            fontSize: 52,
            fontWeight: 700,
            color: "#ffffff",
            maxWidth: 900,
            lineHeight: 1.15,
          }}
        >
          The secure AI operating system for European SMEs
        </div>
        <div style={{ fontSize: 26, color: "#96a3bd", marginTop: 28, maxWidth: 840 }}>
          Compliance, security, sales, support, and automation — from one governed workspace.
        </div>
        {/* The mark's own sweep as a closing rule. */}
        <div
          style={{
            display: "flex",
            width: 320,
            height: 5,
            marginTop: 44,
            borderRadius: 3,
            background: "linear-gradient(100deg, #0d9488 0%, #22d3ee 34%, #818cf8 66%, #1d4ed8 100%)",
          }}
        />
      </div>
    ),
    { ...size },
  );
}
