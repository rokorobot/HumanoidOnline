/**
 * Emergency Compare Crawl Containment (v0.2, 2026-08-22) — v0.1 disabled
 * Next.js's own automatic Link prefetch (prefetch={false}) on the three
 * combinatorial/dynamic compare links. Production evidence gathered AFTER
 * that deploy still showed the same request pattern: bursts of
 * /robots?compare= roughly every 0.5s, repeated /compare?ids= with permuted
 * robot sets. Root cause: `next/link`'s `prefetch` prop only controls Next's
 * own background fetch — it does not change the fact that the component still
 * renders a genuine `<a href>` in server-rendered HTML. Any mechanism that
 * parses that HTML and follows anchors (independent of Next's JS runtime,
 * independent of the prefetch setting) would reproduce exactly this pattern.
 * No `router.prefetch()` call exists anywhere in this codebase, ruling out
 * another client-side mechanism.
 *
 * The fix: replace the anchor with a real `<button>` (components/CompareLink.tsx)
 * that only calls `router.push` on an explicit click. These tests prove, for
 * each of the three sites, that no `<a href>` pointing at the compare
 * destination exists in the rendered output, that a click still navigates to
 * the exact expected URL, and that ordinary (non-compare) navigation is
 * unaffected.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const pushMock = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock, replace: vi.fn() }),
}));

import { CompareBar } from "@/components/CompareBar";
import { CompareLink } from "@/components/CompareLink";
import { RobotCard } from "@/components/RobotCard";
import type { RobotListItem } from "@/lib/types";

function robot(overrides: Partial<RobotListItem> = {}): RobotListItem {
  return {
    id: "r1",
    slug: "unitree-g1",
    name: "G1",
    manufacturer: { slug: "unitree", name: "Unitree" },
    commercial_status: "COMMERCIAL",
    payload_kg: 3,
    height_cm: 130,
    mobility: "BIPEDAL",
    price_display: null,
    available_modes: [],
    deployment_count: 0,
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

beforeEach(() => {
  pushMock.mockClear();
});
afterEach(cleanup);

describe("CompareLink — the shared button behind all three sites", () => {
  it("renders a real <button>, never an <a>, for the given href", () => {
    const { container } = render(
      <CompareLink href="/compare?ids=a,b" className="btn">
        Open comparison →
      </CompareLink>,
    );
    expect(container.querySelector("a")).toBeNull();
    const button = container.querySelector("button");
    expect(button).toBeTruthy();
    expect(button?.getAttribute("type")).toBe("button");
  });

  it("navigates via router.push to the exact href only on click", () => {
    render(
      <CompareLink href="/compare?ids=a,b,c,d" className="btn">
        Open comparison →
      </CompareLink>,
    );
    expect(pushMock).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Open comparison →" }));
    expect(pushMock).toHaveBeenCalledTimes(1);
    expect(pushMock).toHaveBeenCalledWith("/compare?ids=a,b,c,d");
  });

  it("uses the ariaLabel as the accessible name when provided", () => {
    render(
      <CompareLink href="/robots?compare=a,b" ariaLabel="Remove from compare">
        In compare ✓
      </CompareLink>,
    );
    expect(
      screen.getByRole("button", { name: "Remove from compare" }),
    ).toBeTruthy();
  });
});

describe("RobotCard — the combinatorial compare toggle is no longer a crawlable anchor", () => {
  it("renders no <a href> pointing at the compare destination", () => {
    const { container } = render(
      <RobotCard
        robot={robot()}
        compareHref="/robots?compare=unitree-g1,digit"
        inCompare={false}
      />,
    );
    expect(container.querySelector('a[href*="compare="]')).toBeNull();
  });

  it("a click on the compare button navigates to the exact href computed by the caller", () => {
    render(
      <RobotCard
        robot={robot()}
        compareHref="/robots?compare=a,b,c,d"
        inCompare
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Remove from compare" }));
    expect(pushMock).toHaveBeenCalledWith("/robots?compare=a,b,c,d");
  });

  it("ordinary navigation links (image, name) remain real anchors, untouched", () => {
    const { container } = render(<RobotCard robot={robot()} />);
    const detailLinks = container.querySelectorAll('a[href="/robots/unitree-g1"]');
    // image link + name link (+ the fallback "Detail →" when no compareHref).
    expect(detailLinks.length).toBeGreaterThanOrEqual(2);
  });

  it("without a compareHref, falls back to a real anchor (not a button)", () => {
    const { container } = render(<RobotCard robot={robot()} />);
    expect(pushMock).not.toHaveBeenCalled();
    const fallback = container.querySelector('a.cmp[href="/robots/unitree-g1"]');
    expect(fallback).toBeTruthy();
  });
});

describe("CompareBar — Open comparison is no longer a crawlable anchor", () => {
  it("renders no <a href> for the compare destination; button navigates on click", () => {
    const { container } = render(<CompareBar slugs={["unitree-g1", "digit"]} />);
    expect(container.querySelector('a[href*="/compare?ids="]')).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Open comparison →" }));
    expect(pushMock).toHaveBeenCalledWith("/compare?ids=unitree-g1,digit");
  });

  it("renders nothing (no button, no link) below 2 selections", () => {
    const { container } = render(<CompareBar slugs={["unitree-g1"]} />);
    expect(container.querySelector('a[href*="/compare"]')).toBeNull();
    expect(screen.queryByRole("button", { name: "Open comparison →" })).toBeNull();
  });
});

// MatchesCommercial is a complex client component (sessionStorage, a modal
// dialog) — its "Compare these →" action is pinned at the source level rather
// than through a full render, matching this repo's precedent for config
// assertions (__tests__/netlify-config.test.ts).
describe("MatchesCommercial — Compare these is no longer a crawlable anchor", () => {
  const webRoot = resolve(process.cwd());
  const read = (rel: string) => readFileSync(resolve(webRoot, rel), "utf8");

  it("uses CompareLink (a button), not a raw Link, for the compare action", () => {
    const src = read("components/MatchesCommercial.tsx");
    expect(src).toMatch(/<CompareLink className="btn btn--ghost" href=\{compareHref\}>/);
    // No plain <Link ... href={compareHref} ...> survives anywhere in the file.
    expect(src).not.toMatch(/<Link[^>]*href=\{compareHref\}/);
  });

  it("ordinary navigation (adjustHref, Browse robots) is still a plain Link, untouched", () => {
    const src = read("components/MatchesCommercial.tsx");
    expect(src).toMatch(/<Link className="btn" href=\{adjustHref\}>/);
    expect(src).toMatch(/<Link className="btn" href="\/robots">/);
  });
});

// Deliberately unchanged: a single, static, non-combinatorial link — not the
// confirmed amplification mechanism, so it stays a real, indexable/shareable
// anchor exactly as before.
describe("Robot detail page — single static compare link remains a real anchor", () => {
  const webRoot = resolve(process.cwd());
  const read = (rel: string) => readFileSync(resolve(webRoot, rel), "utf8");

  it("still renders a plain Link, not CompareLink, for the single-robot Compare+ action", () => {
    const src = read("app/robots/[slug]/page.tsx");
    const compareLinkLine = src
      .split("\n")
      .find((l) => l.includes(`href={\`/compare?ids=`));
    expect(compareLinkLine).toBeTruthy();
    expect(compareLinkLine).toContain("Link");
    expect(compareLinkLine).not.toContain("CompareLink");
  });
});
