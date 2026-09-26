// SiteNav — the restrained PERMANENT nav (system header). One row:
// HUMANOIDONLINE · ROBOTS · COMPARE · MANUFACTURERS · USE CASES · ABOUT · FIND A HUMANOID.
// Orange marks the active section. No bulky SaaS navbar. Two registers:
// `light` (data pages) and `dark` (used inside the hero/identity top strips).
import Link from "next/link";

import { GraphicMarker } from "./GraphicMarker";

export type NavSection =
  | "robots"
  | "compare"
  | "manufacturers"
  | "use-cases"
  | "about"
  | "find"
  | null;

const LINKS: { key: Exclude<NavSection, null>; href: string; label: string }[] = [
  { key: "robots", href: "/robots", label: "Robots" },
  { key: "compare", href: "/compare", label: "Compare" },
  { key: "manufacturers", href: "/manufacturers", label: "Manufacturers" },
  { key: "use-cases", href: "/use-cases", label: "Use Cases" },
  { key: "about", href: "/about", label: "About" },
];

export function SiteNav({ active = null }: { active?: NavSection }) {
  return (
    <header className="site-head">
      <div className="logo">
        <Link href="/" aria-label="HumanoidOnline home">
          <b>HUMANOIDONLINE</b>
        </Link>
      </div>
      <nav className="nav" aria-label="Primary">
        {LINKS.map((l) => (
          <Link
            key={l.key}
            href={l.href}
            aria-current={active === l.key ? "page" : undefined}
          >
            {l.label}
          </Link>
        ))}
        <Link
          className="cta"
          href="/find-a-humanoid"
          aria-current={active === "find" ? "page" : undefined}
        >
          <GraphicMarker /> Find a Humanoid
        </Link>
      </nav>
    </header>
  );
}

// Dark-register nav row used inside hero / identity top strips.
export function DarkNav({ active = null }: { active?: NavSection }) {
  return (
    <nav className="darknav" aria-label="Primary">
      <Link href="/robots" aria-current={active === "robots" ? "page" : undefined}>
        Robots
      </Link>
      <Link href="/compare" aria-current={active === "compare" ? "page" : undefined}>
        Compare
      </Link>
      <Link
        href="/manufacturers"
        aria-current={active === "manufacturers" ? "page" : undefined}
      >
        Manufacturers
      </Link>
      <Link
        href="/use-cases"
        aria-current={active === "use-cases" ? "page" : undefined}
      >
        Use Cases
      </Link>
      <Link href="/about" aria-current={active === "about" ? "page" : undefined}>
        About
      </Link>
      <Link href="/find-a-humanoid" aria-current={active === "find" ? "page" : undefined}>
        Find a Humanoid
      </Link>
    </nav>
  );
}

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
          COMMERCIAL INTELLIGENCE · MATURITY / OBTAINABILITY / EVIDENCE — KEPT
          INDEPENDENT
        </span>
        <span className="ho-chip">WS3 / INTELLIGENCE UI</span>
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
            {FOOTER_LINKS.map((l) => (
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
