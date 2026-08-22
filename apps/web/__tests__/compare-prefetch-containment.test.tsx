/**
 * Emergency Compare Traffic Containment (2026-08-22) — production evidence
 * showed bursts of requests to /compare?ids= and /robots?compare= within a
 * couple of minutes, including the same robot sets in different permutations.
 * Root cause: RobotCard renders one DISTINCT compareHref per card (up to ~100
 * on a full /robots page — one toggled slug apart from every other card), and
 * CompareBar's target changes on every toggle — both as plain <Link> with
 * Next's default (viewport-triggered) prefetch, so scrolling alone could issue
 * many of these requests with no click.
 *
 * These tests mock next/link to record the exact props each render call
 * receives (prefetch is consumed internally by Next's router and never
 * reaches the DOM, so it can't be asserted from rendered HTML alone) and
 * prove: the combinatorial/dynamic comparison links now set prefetch={false},
 * while ordinary navigation links are untouched — never a global prefetch
 * disable.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { cleanup, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

interface RecordedLink {
  href: string;
  prefetch?: boolean;
  text: string;
}

let recordedLinks: RecordedLink[];

vi.mock("next/link", () => ({
  default: ({
    href,
    prefetch,
    children,
    ...rest
  }: {
    href: string;
    prefetch?: boolean;
    children: React.ReactNode;
    [key: string]: unknown;
  }) => {
    recordedLinks.push({
      href: String(href),
      prefetch,
      text: typeof children === "string" ? children : "",
    });
    return (
      <a href={String(href)} {...rest}>
        {children}
      </a>
    );
  },
}));

import { CompareBar } from "@/components/CompareBar";
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
  recordedLinks = [];
});
afterEach(cleanup);

describe("RobotCard — the combinatorial compare toggle link", () => {
  it("disables prefetch on the compare-toggle link (one distinct href per card)", () => {
    render(
      <RobotCard
        robot={robot()}
        compareHref="/robots?compare=unitree-g1,digit"
        inCompare={false}
      />,
    );
    const cmp = recordedLinks.find((l) => l.href.startsWith("/robots?compare="));
    expect(cmp).toBeTruthy();
    expect(cmp?.prefetch).toBe(false);
  });

  it("does NOT disable prefetch on ordinary navigation links (name, detail)", () => {
    // No compareHref -> the card renders its plain "Detail →" link instead.
    render(<RobotCard robot={robot()} />);
    const nonCompareLinks = recordedLinks.filter(
      (l) => !l.href.includes("compare"),
    );
    expect(nonCompareLinks.length).toBeGreaterThan(0);
    for (const link of nonCompareLinks) {
      // Untouched: no explicit prefetch={false} was introduced here.
      expect(link.prefetch).toBeUndefined();
    }
  });

  it("still points at the exact href the caller computed (no URL rewriting)", () => {
    render(
      <RobotCard
        robot={robot()}
        compareHref="/robots?compare=a,b,c,d"
        inCompare
      />,
    );
    const cmp = recordedLinks.find((l) => l.href === "/robots?compare=a,b,c,d");
    expect(cmp).toBeTruthy();
    expect(cmp?.prefetch).toBe(false);
  });
});

describe("CompareBar — the live-selection compare link", () => {
  it("disables prefetch on the /compare?ids= link", () => {
    render(<CompareBar slugs={["unitree-g1", "digit"]} />);
    const cmp = recordedLinks.find((l) => l.href.startsWith("/compare?ids="));
    expect(cmp).toBeTruthy();
    expect(cmp?.href).toBe("/compare?ids=unitree-g1,digit");
    expect(cmp?.prefetch).toBe(false);
  });

  it("renders no link at all (nothing to prefetch) below 2 selections", () => {
    render(<CompareBar slugs={["unitree-g1"]} />);
    expect(recordedLinks.some((l) => l.href.startsWith("/compare?ids="))).toBe(
      false,
    );
  });
});

// MatchesCommercial is a complex client component (sessionStorage, a modal
// dialog) — its "Compare these →" link is pinned at the source level rather
// than through a full render, matching this repo's precedent for config
// assertions (__tests__/netlify-config.test.ts). Same rationale as CompareBar:
// it points at a compare computation the viewport may not have earned yet.
describe("MatchesCommercial — the ranked-matches compare link", () => {
  const webRoot = resolve(process.cwd());
  const read = (rel: string) => readFileSync(resolve(webRoot, rel), "utf8");

  it("disables prefetch on the /compare?ids= link", () => {
    const src = read("components/MatchesCommercial.tsx");
    expect(src).toMatch(
      /href=\{compareHref\}\s+prefetch=\{false\}/,
    );
  });
});

// Confirms the fix was NOT a blanket prefetch disable: the single, static,
// non-combinatorial compare link on the robot detail page was deliberately
// left untouched (no direct evidence it contributes to the amplification —
// it is one fixed link per page, not one-per-card).
describe("Robot detail page — single static compare link is untouched", () => {
  const webRoot = resolve(process.cwd());
  const read = (rel: string) => readFileSync(resolve(webRoot, rel), "utf8");

  it("does not disable prefetch on the single-robot Compare+ link", () => {
    const src = read("app/robots/[slug]/page.tsx");
    const compareLinkLine = src
      .split("\n")
      .find((l) => l.includes(`href={\`/compare?ids=`));
    expect(compareLinkLine).toBeTruthy();
    expect(compareLinkLine).not.toContain("prefetch");
  });
});
