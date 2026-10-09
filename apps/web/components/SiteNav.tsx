// SiteNav — the restrained PERMANENT nav (system header). One row:
// HUMANOIDONLINE · ROBOTS · COMPARE · MANUFACTURERS · USE CASES · [RESEARCH] · ABOUT · FIND A
// HUMANOID. RESEARCH is shown only once a Research Resource is published.
// Orange marks the active section. No bulky SaaS navbar. Two registers:
// `light` (data pages) and `dark` (used inside the hero/identity top strips).
import Link from "next/link";

import { GraphicMarker } from "./GraphicMarker";
import { MobileMenu, type MenuLink } from "./MobileMenu";
import { NavLink } from "./NavLink";

import { primaryLinks, type NavSection } from "./nav-links";

export type { NavSection };

function menuLinks(active: NavSection): MenuLink[] {
  return [
    ...primaryLinks().map((l) => ({
      key: l.key,
      href: l.href,
      label: l.label,
      current: active === l.key,
    })),
    {
      key: "find",
      href: "/find-a-humanoid",
      label: "Find a Humanoid",
      current: active === "find",
      cta: true,
    },
  ];
}

export function SiteNav({ active = null }: { active?: NavSection }) {
  return (
    <header className="site-head">
      <div className="logo">
        <Link href="/" aria-label="HumanoidOnline home">
          <b>HUMANOIDONLINE</b>
        </Link>
      </div>
      <nav className="nav" aria-label="Primary">
        {primaryLinks().map((l) => (
          <NavLink key={l.key} href={l.href} current={active === l.key}>
            {l.label}
          </NavLink>
        ))}
        <Link
          className="cta"
          href="/find-a-humanoid"
          aria-current={active === "find" ? "page" : undefined}
        >
          <GraphicMarker /> Find a Humanoid
        </Link>
      </nav>
      <MobileMenu links={menuLinks(active)} register="light" />
    </header>
  );
}

// Dark-register nav row used inside hero / identity top strips.
export function DarkNav({ active = null }: { active?: NavSection }) {
  return (
    <>
      <nav className="darknav" aria-label="Primary">
        {menuLinks(active).map((l) => (
          <NavLink key={l.key} href={l.href} current={l.current}>
            {l.label}
          </NavLink>
        ))}
      </nav>
      <MobileMenu links={menuLinks(active)} register="dark" />
    </>
  );
}

// Re-exported for existing importers; the root layout imports it from ./SiteFooter directly.
export { SiteFooter } from "./SiteFooter";
