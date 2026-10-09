// The "Offer market" control (`docs/20` §12.1) — what it emits, and what it
// must never imply.
//
// This filter exists because a German supplier's DE offer is invisible to
// `region=EU`, correctly, while an EU buyer still wants to find it. Two things
// therefore have to hold in the UI, not just the API: the control must be
// UNSET by default (owner decision — no listing is hidden until the buyer
// narrows), and its visible wording must not promise delivery or claim the unit
// is an EU edition. The second is a data-integrity property, so it is tested
// rather than left to review.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

import { FilterPanel } from "@/components/FilterPanel";

function pushedQuery(): URLSearchParams {
  expect(push).toHaveBeenCalled();
  const url = String(push.mock.calls.at(-1)?.[0]);
  return new URLSearchParams(url.split("?")[1] ?? "");
}

beforeEach(() => push.mockClear());
afterEach(cleanup);

describe("offer market control", () => {
  it("is unset by default, so nothing is hidden until the buyer narrows", () => {
    render(<FilterPanel params={{}} resultCount={0} />);
    const select = screen.getByLabelText(/offer market/i) as HTMLSelectElement;
    expect(select.value).toBe("");
    fireEvent.click(screen.getByRole("button", { name: /apply/i }));
    expect(pushedQuery().has("offered_in")).toBe(false);
  });

  it("emits offered_in when a market is chosen", () => {
    render(<FilterPanel params={{}} resultCount={0} />);
    fireEvent.change(screen.getByLabelText(/offer market/i), {
      target: { value: "EU" },
    });
    expect(pushedQuery().get("offered_in")).toBe("EU");
  });

  it("restores the chosen market from the URL", () => {
    render(<FilterPanel params={{ offered_in: "EU" }} resultCount={0} />);
    const select = screen.getByLabelText(/offer market/i) as HTMLSelectElement;
    expect(select.value).toBe("EU");
  });

  it("drops the filter again when returned to Any market", () => {
    render(<FilterPanel params={{ offered_in: "EU" }} resultCount={0} />);
    fireEvent.change(screen.getByLabelText(/offer market/i), {
      target: { value: "" },
    });
    expect(pushedQuery().has("offered_in")).toBe(false);
  });

  it("stays orthogonal to the region filter — both can be active at once", () => {
    // They answer different questions (eligibility vs. market discovery), so
    // setting one must never clear or overwrite the other.
    render(<FilterPanel params={{ region: "DE" }} resultCount={0} />);
    fireEvent.change(screen.getByLabelText(/offer market/i), {
      target: { value: "EU" },
    });
    const q = pushedQuery();
    expect(q.get("region")).toBe("DE");
    expect(q.get("offered_in")).toBe("EU");
  });

  it("promises no delivery and asserts no edition in its visible help text", () => {
    render(<FilterPanel params={{}} resultCount={0} />);
    const help = screen.getByLabelText(/offer market/i).getAttribute("aria-describedby");
    expect(help).toBeTruthy();
    const text = document.getElementById(help!)?.textContent ?? "";
    expect(text).toMatch(/not a delivery guarantee/i);
    expect(text).toMatch(/edition/i);
  });
});

// UX-02D - help next to the two geography controls. The wording is derived from the real
// predicates (apps/api/app/services/robot_filters.py: `region` = a current accessible
// availability offer applying to the region; `offered_in` = a current pricing OR availability
// record tied to the market) and must never imply delivery or turn missing data into "unavailable".
import { MARKET_HELP, REGION_HELP } from "@/components/FilterPanel";
import { countActiveFilters } from "@/lib/search-params";

describe("region / offer market help (UX-02D)", () => {
  it("is a button disclosure: closed by default, aria-expanded + aria-controls, toggles open and shut", () => {
    render(<FilterPanel params={{}} resultCount={0} />);
    const region = screen.getByRole("button", { name: "Region help" });
    const market = screen.getByRole("button", { name: "Offer market help" });
    expect(region.getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByText(REGION_HELP)).toBeNull();
    fireEvent.click(region);
    expect(region.getAttribute("aria-expanded")).toBe("true");
    const panel = screen.getByText(REGION_HELP);
    expect(panel.id).toBe(region.getAttribute("aria-controls"));
    // the other control's help is independent
    expect(market.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(market);
    expect(screen.getByText(MARKET_HELP)).toBeTruthy();
    fireEvent.click(region);
    expect(screen.queryByText(REGION_HELP)).toBeNull();
  });

  it("states the limits: not proof of purchase, no delivery/customs claim, missing data is unknown", () => {
    for (const text of [REGION_HELP, MARKET_HELP]) {
      expect(text).toMatch(/shipping, customs or delivery|ordered, shipped or cleared through customs/);
      expect(text).toMatch(/unknown, not unavailable/);
      expect(text).not.toMatch(/guarantee|will be delivered|ships to/i);
    }
    expect(REGION_HELP).toMatch(/not proof that the robot can be bought there/);
    // the real predicates: region = accessible AVAILABILITY offer incl. wider area + worldwide + unspecified
    expect(REGION_HELP).toMatch(/wider area/);
    expect(REGION_HELP).toMatch(/worldwide/);
    expect(REGION_HELP).toMatch(/no region recorded/);
    // offer market = price OR availability entry, incl. member countries, whatever its status
    expect(MARKET_HELP).toMatch(/price or availability entry/);
    expect(MARKET_HELP).toMatch(/member countries/);
    expect(MARKET_HELP).toMatch(/whatever the entry's status/);
  });

  it("changes no filtering: region only / market only / both map to the same params as before", () => {
    render(<FilterPanel params={{}} resultCount={0} />);
    fireEvent.change(screen.getByLabelText(/^region$/i), { target: { value: "DE" } });
    let q = pushedQuery();
    expect(q.get("region")).toBe("DE");
    expect(q.has("offered_in")).toBe(false);
    fireEvent.change(screen.getByLabelText(/offer market/i), { target: { value: "EU" } });
    q = pushedQuery();
    expect(q.get("region")).toBe("DE");
    expect(q.get("offered_in")).toBe("EU");
    fireEvent.change(screen.getByLabelText(/^region$/i), { target: { value: "" } });
    q = pushedQuery();
    expect(q.has("region")).toBe(false);
    expect(q.get("offered_in")).toBe("EU");
  });

  it("counts region and offer market as two separate active filters", () => {
    expect(countActiveFilters({ region: "DE" })).toBe(1);
    expect(countActiveFilters({ offered_in: "EU" })).toBe(1);
    expect(countActiveFilters({ region: "DE", offered_in: "EU" })).toBe(2);
    expect(countActiveFilters({})).toBe(0);
  });

  it("shows the active count on the mobile toggle", () => {
    render(<FilterPanel params={{ region: "DE", offered_in: "EU" }} resultCount={3} activeCount={2} />);
    expect(screen.getByRole("button", { name: /^Filters/ }).textContent).toContain("Filters · 2 active");
  });
});
