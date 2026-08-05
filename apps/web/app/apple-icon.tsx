import { ImageResponse } from "next/og";

export const size = { width: 180, height: 180 };
export const contentType = "image/png";

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
          background: "#4f46e5",
        }}
      >
        <svg width="132" height="132" viewBox="0 0 32 32" fill="none">
          <circle cx="16" cy="16" r="8.5" stroke="white" strokeOpacity="0.9" strokeWidth="1.6" />
          <circle cx="16" cy="16" r="2.5" fill="white" />
          <circle cx="23" cy="16" r="1.6" fill="white" />
          <circle cx="9" cy="16" r="1.6" fill="white" />
          <circle cx="16" cy="9" r="1.6" fill="white" />
          <circle cx="16" cy="23" r="1.6" fill="white" />
        </svg>
      </div>
    ),
    { ...size },
  );
}
