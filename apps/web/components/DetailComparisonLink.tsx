"use client";

// UX-02C - comparison continuity on the robot detail page (ONE client component, so the page
// adds a single client reference to its payload).
//
// The compare selection is carried in the URL (`/robots/<slug>?compare=a,b`) and read ONLY on
// the client after mount: the server component never reads searchParams, so the page's
// server output, caching and render mode are exactly what they were. No storage.
//   - the existing "Compare +" action: server HTML keeps its plain `/compare?ids=<this robot>`
//     href (one static anchor, as before). With a carried selection a click toggles THIS robot
//     in it in place; with none it navigates as before.
//   - a small tray, rendered only when a selection is carried (client-rendered, so it adds
//     nothing to the delivered document).
//   - click delegation for server-rendered plain links in the breadcrumb (`.idcrumb`, "Robot Catalogue"): they keep their plain href and carry the selection on click.
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { nameFromSlug } from "@/lib/labels";
import { MAX_COMPARE, resolveNavTarget, selectionFromLocation, toggleSlug } from "@/lib/nav-selection";

import { GraphicMarker } from "./GraphicMarker";

const EVENT = "ho:compare-selection";

function readSelection(): string[] {
  return selectionFromLocation(window.location.pathname, window.location.search);
}

function writeSelection(selection: string[]) {
  const url = new URL(window.location.href);
  if (selection.length) url.searchParams.set("compare", selection.join(","));
  else url.searchParams.delete("compare");
  // replaceState: toggling is not a navigation step, so Back still leaves the page.
  window.history.replaceState(window.history.state, "", `${url.pathname}${url.search}`);
  window.dispatchEvent(new Event(EVENT));
}

export function DetailComparisonLink({ slug, name, href }: { slug: string; name: string; href: string }) {
  const router = useRouter();
  // Held in a ref so the listeners below are registered once, not re-registered per render.
  const routerRef = useRef(router);
  routerRef.current = router;
  const [selection, setSelection] = useState<string[]>([]);
  const sync = useCallback(() => setSelection(readSelection()), []);

  useEffect(() => {
    sync();
    function onClick(e: MouseEvent) {
      if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      const a = (e.target as Element | null)?.closest?.(".idcrumb a");
      if (!a) return;
      const target = resolveNavTarget(a.getAttribute("href") ?? "", window.location.pathname, window.location.search);
      if (target) {
        e.preventDefault();
        routerRef.current.push(target);
      }
    }
    window.addEventListener("popstate", sync);
    window.addEventListener(EVENT, sync);
    // Capture phase: runs before the framework Link handler, which then sees defaultPrevented.
    document.addEventListener("click", onClick, true);
    return () => {
      window.removeEventListener("popstate", sync);
      window.removeEventListener(EVENT, sync);
      document.removeEventListener("click", onClick, true);
    };
  }, [sync]);

  const inSelection = selection.includes(slug);
  const full = !inSelection && selection.length >= MAX_COMPARE;
  const names = selection.map((s) => (s === slug ? name : nameFromSlug(s)));
  return (
    <>
      <Link
        className="btn"
        href={href}
        onClick={(e) => {
          if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
          const current = readSelection();
          if (current.length === 0) return; // no carried selection: navigate as before
          e.preventDefault();
          writeSelection(toggleSlug(current, slug));
        }}
      >
        <GraphicMarker />{" "}
        {selection.length > 0 && inSelection ? "In compare ✓ (remove)" : selection.length > 0 && full ? "Compare full (4)" : "Compare +"}
      </Link>
      {selection.length > 0 && (
        <div className="cmp-tray" role="region" aria-label="Compare selection">
          <span className="ho-syslabel">
            Compare selection: {selection.length} / {MAX_COMPARE} {"—"} {names.join(" · ")}
          </span>
          {selection.length >= 2 ? (
            <button
              type="button"
              className="btn btn--signal"
              onClick={() => router.push(`/compare?ids=${selection.join(",")}`)}
            >
              Open comparison {"→"}
            </button>
          ) : (
            <span className="ho-syslabel">Select at least 2 to compare</span>
          )}
        </div>
      )}
    </>
  );
}
