import type { Metadata } from "next";
import type { ReactNode } from "react";

import { SiteFooter } from "@/components/SiteNav";

import "./tokens.css";
import "./globals.css";

// WS8.5 / R22 — a title template so every child route gets a specific title and
// none inherits a bare generic root title. `default` is the home title; child
// pages set a short `title` and render as "<title> — HumanoidOnline".
export const metadata: Metadata = {
  title: {
    default: "HumanoidOnline — Commercial intelligence for the humanoid market",
    template: "%s — HumanoidOnline",
  },
  description:
    "Compare capabilities, commercial availability, pricing and deployment evidence across the humanoid-robot market. Maturity, obtainability and evidence kept as three independent facts.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <a className="skip-link" href="#main-content">
          Skip to content
        </a>
        {/* tabIndex={-1} so activating the skip link actually MOVES focus to the
            main landmark (WS8.4 / R17 focus behaviour) — a fragment link only
            scrolls to a non-focusable target; without this the keyboard user's
            focus stays on the skip link. -1 keeps it out of the Tab order. */}
        <main id="main-content" tabIndex={-1}>
          {children}
        </main>
        {/* Rendered once here as a SIBLING of <main> (not inside it) so the
            <footer> exposes the contentinfo landmark — a footer nested in <main>
            gets no landmark role (WS8.4 / R17). Pages no longer render their own. */}
        <SiteFooter />
      </body>
    </html>
  );
}
