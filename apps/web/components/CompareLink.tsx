"use client";

// Emergency Compare Crawl Containment (v0.2) — a real <a href> in
// server-rendered HTML is followed by ANY link-parsing mechanism regardless of
// Next.js's own prefetch setting. v0.1's prefetch={false} only stopped Next's
// automatic background fetch; production evidence gathered after that deploy
// still showed the same combinatorial /robots?compare= and /compare?ids=
// request pattern (bursts, permutations, ~0.5s cadence) with no
// router.prefetch() call anywhere in the codebase — the remaining explanation
// is something parsing the anchors directly (bot/crawler/scanner behaviour),
// independent of the browser's JS runtime.
//
// This renders a real, keyboard-accessible <button> in its place: the
// destination only becomes an HTTP request after an explicit user click
// (router.push), never from parsing the page's HTML. Direct, typed, bookmarked
// or shared navigation to the same URL is completely unaffected — this only
// removes the passive DISCOVERY path, not the destination route itself.
import { useRouter } from "next/navigation";
import type { ReactNode } from "react";

export function CompareLink({
  href,
  className,
  ariaLabel,
  children,
}: {
  href: string;
  className?: string;
  ariaLabel?: string;
  children: ReactNode;
}) {
  const router = useRouter();
  return (
    <button
      type="button"
      className={className}
      aria-label={ariaLabel}
      onClick={() => router.push(href)}
    >
      {children}
    </button>
  );
}
