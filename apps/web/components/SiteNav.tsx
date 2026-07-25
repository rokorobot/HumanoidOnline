// SiteNav — the restrained PERMANENT nav (system header). One row:
// HUMANOIDONLINE · ROBOTS · COMPARE · MANUFACTURERS · USE CASES · FIND A HUMANOID.
// Orange marks the active section. No bulky SaaS navbar. Two registers:
// `light` (data pages) and `dark` (used inside the hero/identity top strips).
import Link from "next/link";

import { GraphicMarker } from "./GraphicMarker";

export type NavSection =
  | "robots"
  | "compare"
  | "manufacturers"
  | "use-cases"
  | "find"
  | null;

const LINKS: { key: Exclude<NavSection, null>; href: string; label: string }[] = [
  { key: "robots", href: "/robots", label: "Robots" },
  { key: "compare", href: "/compare", label: "Compare" },
  { key: "manufacturers", href: "/manufacturers", label: "Manufacturers" },
  { key: "use-cases", href: "/use-cases", label: "Use Cases" },
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
      <Link href="/find-a-humanoid" aria-current={active === "find" ? "page" : undefined}>
        Find a Humanoid
      </Link>
    </nav>
  );
}

export function SiteFooter() {
  return (
    <footer className="foot">
      <div className="wrap foot-grid">
        <div>
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
    </footer>
  );
}
