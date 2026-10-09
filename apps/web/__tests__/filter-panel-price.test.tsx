// AGENT-02.1d — the price control's URL emission.
//
// `search-params.test` proves the API params are derived correctly; this proves
// the other half: that the URL the filter rail pushes carries the denomination
// whenever a ceiling is active, and carries neither member once the field is
// cleared. Those are the two states the API contract distinguishes, and a lone
// `price_currency` is invalid — so it must be impossible to produce by using
// the UI, not merely rejected downstream.
//
// The visible label must keep stating the denomination: the UI may only assert
// USD because the user can see it say USD.
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

function apply() {
  fireEvent.click(screen.getByRole("button", { name: /apply/i }));
}

beforeEach(() => push.mockClear());
afterEach(cleanup);

describe("price filter URL emission", () => {
  it("emits price_currency=USD alongside an entered ceiling", () => {
    render(<FilterPanel params={{}} resultCount={0} />);
    fireEvent.change(screen.getByLabelText(/max purchase price/i), {
      target: { value: "30000" },
    });
    apply();

    const q = pushedQuery();
    expect(q.get("price_max")).toBe("30000");
    expect(q.get("price_currency")).toBe("USD");
  });

  it("emits neither member when no price is entered", () => {
    render(<FilterPanel params={{}} resultCount={0} />);
    apply();

    const q = pushedQuery();
    expect(q.has("price_max")).toBe(false);
    expect(q.has("price_currency")).toBe(false);
  });

  it("drops BOTH members when a previously-set price is cleared", () => {
    render(
      <FilterPanel
        params={{ price_max: "30000", price_currency: "USD" }}
        resultCount={0}
      />,
    );
    fireEvent.change(screen.getByLabelText(/max purchase price/i), {
      target: { value: "" },
    });
    apply();

    const q = pushedQuery();
    expect(q.has("price_max")).toBe(false);
    expect(q.has("price_currency")).toBe(false);
  });

  it("never emits a lone price_currency, whatever the incoming URL said", () => {
    // A hand-edited `?price_currency=USD` must not be propagated by using the UI.
    render(<FilterPanel params={{ price_currency: "USD" }} resultCount={0} />);
    apply();
    expect(pushedQuery().has("price_currency")).toBe(false);
  });

  it("preserves the price pair while another filter changes", () => {
    render(<FilterPanel params={{ price_max: "30000" }} resultCount={0} />);
    fireEvent.change(screen.getByLabelText(/mobility/i), {
      target: { value: "BIPEDAL" },
    });

    const q = pushedQuery();
    expect(q.get("mobility")).toBe("BIPEDAL");
    expect(q.get("price_max")).toBe("30000");
    expect(q.get("price_currency")).toBe("USD");
  });

  it("keeps orthogonal state (q, sort) intact alongside the pair", () => {
    render(
      <FilterPanel
        params={{ price_max: "30000", q: "atlas", sort: "-payload" }}
        resultCount={0}
      />,
    );
    apply();

    const q = pushedQuery();
    expect(q.get("q")).toBe("atlas");
    expect(q.get("sort")).toBe("-payload");
    expect(q.get("price_currency")).toBe("USD");
  });
});

describe("price control (UX-02A: the denomination is now an explicit, visible selector)", () => {
  it("states what the number matches and in which currency", () => {
    render(<FilterPanel params={{}} resultCount={0} />);
    const select = screen.getByRole("combobox", { name: /price currency/i }) as HTMLSelectElement;
    expect(select.value).toBe("USD");
    expect(Array.from(select.options).map((o) => o.value)).toEqual(["USD", "EUR", "GBP", "CZK"]);
    expect(screen.getByText(/\(no conversion\)/i)).toBeDefined();
  });

  it("emits the chosen currency with the ceiling, and never a lone currency", () => {
    render(<FilterPanel params={{}} resultCount={0} />);
    fireEvent.change(screen.getByLabelText(/max purchase price/i), { target: { value: "20000" } });
    fireEvent.change(screen.getByRole("combobox", { name: /price currency/i }), { target: { value: "EUR" } });
    apply();
    let q = pushedQuery();
    expect(q.get("price_max")).toBe("20000");
    expect(q.get("price_currency")).toBe("EUR");
    // clearing the ceiling drops the currency with it
    fireEvent.change(screen.getByLabelText(/max purchase price/i), { target: { value: "" } });
    apply();
    q = pushedQuery();
    expect(q.has("price_max")).toBe(false);
    expect(q.has("price_currency")).toBe(false);
  });

  it("restores the price field from a URL carrying the pair", () => {
    render(
      <FilterPanel
        params={{ price_max: "45000", price_currency: "USD" }}
        resultCount={0}
      />,
    );
    const input = screen.getByLabelText(/max purchase price/i) as HTMLInputElement;
    expect(input.value).toBe("45000");
  });
});
