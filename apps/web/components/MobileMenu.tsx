"use client";

// MobileMenu - the one accessible narrow-width navigation used by BOTH header
// registers (UX-01 / P0-C). A real <button aria-expanded aria-controls> opens a
// disclosure panel of the primary links; Escape closes it and returns focus to the
// button; targets are >= 44px. Hidden by CSS above the register's breakpoint,
// where the full inline nav is shown instead.
import { useEffect, useId, useRef, useState } from "react";

import { GraphicMarker } from "./GraphicMarker";
import { NavLink } from "./NavLink";
import { menuLinksFor, type NavSection } from "./nav-model";

export function MobileMenu({
  active = null,
  research = false,
  register,
}: {
  active?: NavSection;
  research?: boolean;
  register: "light" | "dark";
}) {
  const links = menuLinksFor(active, research);
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const buttonRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLElement>(null);

  useEffect(() => {
    if (!open) return;
    panelRef.current?.querySelector<HTMLElement>("a")?.focus();
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        setOpen(false);
        buttonRef.current?.focus();
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <div className={`mmenu mmenu--${register}`}>
      <button
        ref={buttonRef}
        type="button"
        className="mmenu-btn"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((o) => !o)}
      >
        <span aria-hidden="true" className="mmenu-icon">
          <i />
          <i />
          <i />
        </span>
        Menu
      </button>
      {/* Rendered only while open (keeps every page lighter); axe accepts an
          aria-controls that points at a not-yet-rendered id while aria-expanded=false. */}
      {open && (
        <nav id={panelId} ref={panelRef} className="mmenu-panel" aria-label="Menu">
          {links.map((l) => (
            <NavLink
              key={l.key}
              href={l.href}
              current={l.current}
              className={l.cta ? "mmenu-link cta" : "mmenu-link"}
              onNavigate={() => setOpen(false)}
            >
              {l.cta && <GraphicMarker />} {l.label}
            </NavLink>
          ))}
        </nav>
      )}
    </div>
  );
}
