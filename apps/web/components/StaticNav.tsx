// StaticNav - the same header as SiteNav with plain links and NO client components.
// Used by app/not-found.tsx: the not-found boundary belongs to the root layout, so
// anything it imports client-side is added to EVERY route's bundle. A 404 has no
// compare selection to carry and no need for the mobile menu.
import Link from "next/link";

import { GraphicMarker } from "./GraphicMarker";
import { primaryLinks } from "./nav-links";

export function StaticNav() {
  return (
    <header className="site-head">
      <div className="logo">
        <Link href="/" aria-label="HumanoidOnline home">
          <b>HUMANOIDONLINE</b>
        </Link>
      </div>
      <nav className="nav nav--static" aria-label="Primary">
        {primaryLinks().map((l) => (
          <Link key={l.key} href={l.href}>
            {l.label}
          </Link>
        ))}
        <Link className="cta" href="/find-a-humanoid">
          <GraphicMarker /> Find a Humanoid
        </Link>
      </nav>
    </header>
  );
}
