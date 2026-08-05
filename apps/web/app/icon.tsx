import { ImageResponse } from "next/og";

export const size = { width: 32, height: 32 };
export const contentType = "image/png";

export default function Icon() {
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
          borderRadius: 8,
        }}
      >
        <svg width="24" height="24" viewBox="0 0 32 32" fill="none">
          <circle cx="16" cy="16" r="8.5" stroke="white" strokeOpacity="0.9" strokeWidth="1.8" />
          <circle cx="16" cy="16" r="2.6" fill="white" />
          <circle cx="23" cy="16" r="1.7" fill="white" />
          <circle cx="9" cy="16" r="1.7" fill="white" />
          <circle cx="16" cy="9" r="1.7" fill="white" />
          <circle cx="16" cy="23" r="1.7" fill="white" />
        </svg>
      </div>
    ),
    { ...size },
  );
}
