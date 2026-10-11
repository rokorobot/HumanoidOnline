import { ImageResponse } from "next/og";

// SOCIAL-01 — the one site-wide social sharing card (og:image / twitter:image
// for every route). Brand only: the mark, the wordmark and the positioning line
// in the UI-D1 palette. Deliberately no robot photo and no catalogue fact — a
// card is cached by social platforms for a long time, and nothing on it may go
// stale or need provenance.
export const alt = "HumanoidOnline — Commercial intelligence for the humanoid market";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

// tokens.css values; CSS variables are not available to the image renderer.
const INK = "#131210";
const PAPER_INK = "#E7E3D8";
const SIGNAL = "#FF4A00";
const GREY = "#9C968A";

export default function OpengraphImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          backgroundColor: INK,
          color: PAPER_INK,
          padding: 72,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          {/* The app/icon.svg mark. */}
          <svg width="72" height="72" viewBox="0 0 32 32">
            <polygon
              fill={PAPER_INK}
              points="16,3 18.92,11.98 28.36,11.98 20.72,17.53 23.64,26.52 16,20.97 8.36,26.52 11.28,17.53 3.64,11.98 13.08,11.98"
            />
          </svg>
          <div style={{ display: "flex", fontSize: 22, letterSpacing: 6, color: GREY }}>
            CAPABILITY · AVAILABILITY · EVIDENCE
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column" }}>
          <div style={{ display: "flex", fontSize: 112, letterSpacing: -4, lineHeight: 1 }}>
            HumanoidOnline
          </div>
          <div style={{ display: "flex", width: 160, height: 6, backgroundColor: SIGNAL, marginTop: 36 }} />
          <div style={{ display: "flex", fontSize: 44, marginTop: 36, lineHeight: 1.2 }}>
            Commercial intelligence for the humanoid market
          </div>
        </div>
      </div>
    ),
    size,
  );
}
