// SiteFooter - lives in its own module on purpose: the root layout renders it on
// EVERY route, and importing it from SiteNav.tsx would drag SiteNav's client
// components (mobile menu, nav links) into every page's client bundle graph.
import Link from "next/link";

import { researchNavVisible } from "@/lib/research";

// Secondary navigation in the footer's lower band. Plain links — the orange
// Find a Humanoid CTA stays a top-navigation affordance only.
const FOOTER_LINKS: { href: string; label: string }[] = [
  { href: "/robots", label: "Robots" },
  { href: "/compare", label: "Compare" },
  { href: "/manufacturers", label: "Manufacturers" },
  { href: "/use-cases", label: "Use Cases" },
  { href: "/about", label: "About" },
  { href: "/contact", label: "Contact" },
];

export function SiteFooter() {
  const footerLinks = researchNavVisible()
    ? [
        ...FOOTER_LINKS.slice(0, FOOTER_LINKS.findIndex((l) => l.href === "/about")),
        { href: "/research", label: "Research" },
        ...FOOTER_LINKS.slice(FOOTER_LINKS.findIndex((l) => l.href === "/about")),
      ]
    : FOOTER_LINKS;
  return (
    <footer className="foot ho-dark">
      <div className="wrap foot-grid">
        <div>
          <span className="foot-mark" aria-hidden="true" />
          <b>HUMANOIDONLINE</b>
          <span className="foot-brand">
            {" "}· A{" "}
            <a className="foot-brand-link" href="https://humanoid.company/">
              Humanoid.Company
            </a>{" "}
            project
          </span>
        </div>
        <span className="ho-syslabel">
          Commercial intelligence — maturity, obtainability and evidence kept
          independent
        </span>
      </div>
      {/* Lower band: identity/copyright on the left, secondary footer
          navigation on the right (stacks below on narrow viewports). */}
      <div className="wrap foot-legal">
        <div className="foot-id">
          <p>&copy; 2026 Humanoid Company. All rights reserved.</p>
          <p>
            <b>HumanoidOnline</b> is a{" "}
            <a className="foot-brand-link" href="https://humanoid.company/">
              <b>Humanoid.Company</b>
            </a>{" "}
            brand.
          </p>
        </div>
        <nav className="foot-nav" aria-label="Footer">
          <ul>
            {footerLinks.map((l) => (
              <li key={l.href}>
                <Link href={l.href}>{l.label}</Link>
              </li>
            ))}
          </ul>
        </nav>
      </div>
    </footer>
  );
}
