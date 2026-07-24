import type { ReactNode } from "react";

import "./tokens.css";
import "./globals.css";

export const metadata = {
  title: "HumanoidOnline — Commercial intelligence for the humanoid market",
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
        <main id="main-content">{children}</main>
      </body>
    </html>
  );
}
