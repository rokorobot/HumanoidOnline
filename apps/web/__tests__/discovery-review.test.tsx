// DATA-D1 operator review page — NONCANONICAL surface.
//
// What these tests actually protect: that this page can never be mistaken for the
// catalogue. A reviewer glancing at it, or a screenshot of it pasted into a chat,
// must not read as "HumanoidOnline lists these 43 robots".
//
// So the assertions are as much about what is ABSENT as what renders: no Compare,
// no Buy/Rent/Lease, no Find-a-Humanoid, no specs, no price. Those controls are
// the visual grammar of a verified option, and a candidate has not earned it.
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { DiscoveryCandidateReview, Page } from "@/lib/types";

const listDiscoveryCandidates = vi.fn();

vi.mock("@/lib/api-client", () => ({
  listDiscoveryCandidates: (...args: unknown[]) => listDiscoveryCandidates(...args),
}));

// The page gates itself on APP_ENV; the suite runs as "test", which is relaxed.
vi.mock("@/lib/site", () => ({ resolveAppEnv: () => "test" }));

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));
vi.mock("next/navigation", () => ({
  notFound: () => {
    throw new Error("notFound() called");
  },
}));

import DiscoveryReviewPage from "@/app/discovery-review/page";

function candidate(
  over: Partial<DiscoveryCandidateReview> = {},
): DiscoveryCandidateReview {
  return {
    id: "11111111-1111-1111-1111-111111111111",
    candidate_name: "Digit",
    candidate_manufacturer: "Agility Robotics",
    external_ref: "agility/digit",
    discovery_url: "https://www.agilityrobotics.com/",
    official_url: "https://www.agilityrobotics.com/",
    source_name: "Manual bootstrap — humanoid_radar_v1",
    source_class: "OTHER",
    status: "DISCOVERED",
    identity_status: "UNRESOLVED",
    trace_state: "NOT_TRACED",
    discovered_at: "2026-07-29T12:00:00Z",
    last_seen_at: "2026-07-29T12:00:00Z",
    ...over,
  };
}

function page(items: DiscoveryCandidateReview[]): Page<DiscoveryCandidateReview> {
  return { items, total: items.length, limit: 100, offset: 0 };
}

async function renderPage(items: DiscoveryCandidateReview[]) {
  listDiscoveryCandidates.mockResolvedValue(page(items));
  render(await DiscoveryReviewPage());
}

// `globals: false` in vitest.config means Testing Library's auto-cleanup is not
// installed — without this, DOM from one render leaks into the next and queries
// fail with "multiple elements found" rather than anything meaningful.
afterEach(cleanup);

beforeEach(() => {
  listDiscoveryCandidates.mockReset();
});

describe("discovery review page", () => {
  it("renders the candidate and manufacturer counts", async () => {
    await renderPage([
      candidate(),
      candidate({
        id: "2",
        candidate_name: "Atlas",
        candidate_manufacturer: "Boston Dynamics",
        external_ref: "bostondynamics/atlas",
      }),
      candidate({
        id: "3",
        candidate_name: "Optimus",
        candidate_manufacturer: "Tesla",
        external_ref: "tesla/optimus",
      }),
    ]);
    expect(screen.getByText(/3 CANDIDATES · 3 MANUFACTURERS/)).toBeTruthy();
  });

  it("shows the candidate name and manufacturer", async () => {
    await renderPage([candidate()]);
    expect(screen.getByText("Digit")).toBeTruthy();
    expect(screen.getAllByText(/Agility Robotics/).length).toBeGreaterThan(0);
  });

  it("groups candidates by manufacturer", async () => {
    await renderPage([
      candidate(),
      candidate({ id: "2", candidate_name: "Digit v2", external_ref: "agility/digit-2" }),
      candidate({
        id: "3",
        candidate_name: "Atlas",
        candidate_manufacturer: "Boston Dynamics",
        external_ref: "bd/atlas",
      }),
    ]);
    // Two groups, and the Agility group carries its count.
    expect(screen.getByText(/Agility Robotics · 2/)).toBeTruthy();
    expect(screen.getByText(/Boston Dynamics · 1/)).toBeTruthy();
  });

  it("shows the unverified warning prominently", async () => {
    await renderPage([candidate()]);
    const warning = screen.getByTestId("unverified-warning");
    expect(warning.textContent).toMatch(/not verified catalogue entries/i);
    expect(warning.textContent).toMatch(/cannot be used for comparison or commercial/i);
    expect(warning.textContent).toMatch(
      /Specifications, prices, commercial availability, maturity and imagery/i,
    );
  });

  it("renders the queue state verbatim", async () => {
    await renderPage([candidate()]);
    expect(screen.getByText("DISCOVERED")).toBeTruthy();
    expect(screen.getByText("UNRESOLVED")).toBeTruthy();
    expect(screen.getByText("NOT_TRACED")).toBeTruthy();
  });

  it("renders the official URL as an external link", async () => {
    await renderPage([candidate()]);
    const link = screen.getByText(/OFFICIAL URL LEAD/).closest("a");
    expect(link).toBeTruthy();
    expect(link?.getAttribute("href")).toBe("https://www.agilityrobotics.com/");
    expect(link?.getAttribute("target")).toBe("_blank");
    // noopener for safety, nofollow because an unverified lead is not an
    // endorsement we want to pass along.
    expect(link?.getAttribute("rel")).toMatch(/noopener/);
    expect(link?.getAttribute("rel")).toMatch(/nofollow/);
  });

  it("says so honestly when there is no official URL, without a broken link", async () => {
    await renderPage([candidate({ official_url: null })]);
    expect(screen.getByText("NO OFFICIAL URL LEAD RECORDED")).toBeTruthy();
    // No anchor may point nowhere.
    for (const anchor of Array.from(document.querySelectorAll("a"))) {
      const href = anchor.getAttribute("href");
      expect(href === null || href.trim().length > 0).toBe(true);
      expect(href).not.toBe("null");
      expect(href).not.toBe("undefined");
    }
  });

  it("renders NO commercial or comparison action for a candidate", async () => {
    await renderPage([candidate()]);
    const text = document.body.textContent ?? "";
    for (const forbidden of [
      "Compare",
      "COMPARE",
      "Add to compare",
      "Buy",
      "Rent",
      "Lease",
      "Request Availability",
      "Find a humanoid",
      "FIND A HUMANOID",
      "Get a quote",
    ]) {
      expect(text).not.toContain(forbidden);
    }
    // And no interactive control that could act on a candidate.
    expect(document.querySelectorAll("button").length).toBe(0);
    expect(document.querySelectorAll("form").length).toBe(0);
    expect(document.querySelectorAll("input").length).toBe(0);
  });

  it("displays no specification, price, availability or maturity value", async () => {
    await renderPage([candidate()]);
    const text = document.body.textContent ?? "";
    for (const forbidden of [
      "PAYLOAD",
      "HEIGHT",
      "MOBILITY",
      "PRICE",
      "QUOTE_ONLY",
      "AVAILABLE",
      "COMMERCIAL",
      "RAAS_DEPLOYMENT",
      "$",
    ]) {
      expect(text).not.toContain(forbidden);
    }
  });

  it("renders a valid empty state", async () => {
    await renderPage([]);
    expect(screen.getByTestId("empty-state").textContent).toMatch(
      /No discovery candidates on record/i,
    );
    // The warning stays visible even with nothing listed.
    expect(screen.getByTestId("unverified-warning")).toBeTruthy();
    expect(screen.getByText(/0 CANDIDATES · 0 MANUFACTURERS/)).toBeTruthy();
  });

  it("keeps the verified catalogue clearly separate and linked", async () => {
    await renderPage([candidate()]);
    const back = screen.getByText(/VERIFIED ROBOT CATALOGUE/).closest("a");
    expect(back?.getAttribute("href")).toBe("/robots");
    // The heading names the surface for what it is.
    expect(screen.getByRole("heading", { level: 1 }).textContent).toMatch(
      /Discovery review/i,
    );
  });

  it("renders an unnamed candidate honestly rather than blank", async () => {
    await renderPage([candidate({ candidate_name: null })]);
    expect(screen.getByText("UNNAMED CANDIDATE")).toBeTruthy();
  });

  it("requests a bounded page rather than everything", async () => {
    await renderPage([candidate()]);
    expect(listDiscoveryCandidates).toHaveBeenCalledWith({ limit: 100 });
  });
});
