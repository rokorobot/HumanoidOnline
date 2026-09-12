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
