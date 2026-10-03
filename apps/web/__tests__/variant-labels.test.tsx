import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { AvailabilityMatrix } from "../components/AvailabilityState";
import type { AvailabilityOffer } from "../lib/types";

const offer = (variant: string | null): AvailabilityOffer => ({
  transaction_type: "PURCHASE",
  availability_status: "WAITLIST",
  variant,
  variant_slug: variant ? variant.toLowerCase() : null,
  delivery_estimate_label: "Expected in 2026",
  seller_wording: "Both are expected to be available in 2026.",
});

afterEach(cleanup);

describe("variant-scoped availability", () => {
  it("names the configuration of each row and shows year-level wording only", () => {
    render(<AvailabilityMatrix offers={[offer("Standard"), offer("Pro")]} />);
    expect(screen.getByText("Standard configuration")).toBeTruthy();
    expect(screen.getByText("Pro configuration")).toBeTruthy();
    expect(screen.getAllByText("WAITLIST").length).toBe(2);
    expect(screen.getAllByText("Expected in 2026").length).toBe(2);
    expect(document.body.textContent).not.toMatch(/2026-\d\d/); // no invented date
  });

  it("shows no configuration label for a whole-robot offer", () => {
    render(<AvailabilityMatrix offers={[offer(null)]} />);
    expect(screen.queryByText(/configuration/)).toBeNull();
  });
});
