"use client";

// Header nav link that keeps the compare selection alive across the Robots <->
// Compare hop (UX-01 / P0-D). The server HTML is an ordinary
// `<a href="/compare">` / `<a href="/robots">` - never a selection-carrying URL,
// so the crawl-containment rule (components/CompareLink.tsx) is untouched. Only
// on an explicit click do we read the CURRENT URL (window.location, no
// useSearchParams, so static pages are not forced into client-side rendering)
// and router.push to the equivalent URL when it holds a selection.
import Link from "next/link";
import { useRouter } from "next/navigation";
import type { ReactNode } from "react";

import { resolveNavTarget } from "@/lib/nav-selection";

export function NavLink({
  href,
  className,
  current,
  onNavigate,
  children,
}: {
  href: string;
  className?: string;
  current?: boolean;
  onNavigate?: () => void;
  children: ReactNode;
}) {
  const router = useRouter();
  return (
    <Link
      href={href}
      className={className}
      aria-current={current ? "page" : undefined}
      onClick={(e) => {
        onNavigate?.();
        if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) {
          return;
        }
        const target = resolveNavTarget(href, window.location.pathname, window.location.search);
        if (target) {
          e.preventDefault();
          router.push(target);
        }
      }}
    >
      {children}
    </Link>
  );
}
