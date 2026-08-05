import { ImageResponse } from "next/og";

export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

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
          background: "#f8fafc",
          fontFamily: "sans-serif",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 40 }}>
          <div
            style={{
              width: 56,
              height: 56,
              borderRadius: 14,
              background: "#4f46e5",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <svg width="38" height="38" viewBox="0 0 32 32" fill="none">
              <circle cx="16" cy="16" r="8.5" stroke="white" strokeOpacity="0.9" strokeWidth="1.6" />
              <circle cx="16" cy="16" r="2.5" fill="white" />
              <circle cx="23" cy="16" r="1.6" fill="white" />
              <circle cx="9" cy="16" r="1.6" fill="white" />
              <circle cx="16" cy="9" r="1.6" fill="white" />
              <circle cx="16" cy="23" r="1.6" fill="white" />
            </svg>
          </div>
          <div style={{ fontSize: 34, fontWeight: 700, color: "#0f172a" }}>Agora Origin</div>
        </div>
        <div style={{ fontSize: 44, fontWeight: 700, color: "#0f172a", maxWidth: 880, lineHeight: 1.2 }}>
          The secure AI operating system for European SMEs
        </div>
        <div style={{ fontSize: 24, color: "#475569", marginTop: 24, maxWidth: 820 }}>
          Compliance, security, sales, support, and automation — from one governed workspace.
        </div>
      </div>
    ),
    { ...size },
  );
}
