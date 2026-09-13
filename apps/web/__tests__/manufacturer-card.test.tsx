/**
 * ManufacturerCard — the derived status must speak for PUBLISHED catalogue
 * models only, and the tracked/published counts stay two labelled facts.
 *
 * The regression this pins: a maker whose only published model is retired
 * rendered "PORTFOLIO: DISCONTINUED", which reads as a verdict on the company.
 */
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { ManufacturerCard } from "../components/ManufacturerCard";
import type { ManufacturerListItem } from "../lib/types";

function item(overrides: Partial<ManufacturerListItem>): ManufacturerListItem {
  return {
    slug: "test-maker",
    name: "Test Maker",
    country: "US",
    tracked_robot_count: 3,
    published_robot_count: 1,
    deployment_status: "COMMERCIAL",
    portfolio_status: "DISCONTINUED",
    updated_at: "2026-09-13T00:00:00Z",
    ...overrides,
  };
}

describe("ManufacturerCard — published model status", () => {
  afterEach(cleanup);

  it("scopes an all-discontinued result to published models, never the maker", () => {
    const { container } = render(<ManufacturerCard manufacturer={item({})} />);
    const text = container.textContent ?? "";
    expect(text).toContain("PUBLISHED MODEL STATUS");
    expect(text).toContain("ALL DISCONTINUED");
    expect(text).not.toContain("PORTFOLIO");
    expect(text).toContain("CATALOGUE MODELS");
    expect(text).toContain("3 TRACKED · 1 PUBLISHED");
    // The company's humanoid deployment column is not what the card shows.
    expect(text).not.toContain("COMMERCIAL");
  });

  it("says NONE PUBLISHED when no catalogue model is published", () => {
    const { container } = render(
      <ManufacturerCard
        manufacturer={item({ published_robot_count: 0, portfolio_status: null, tracked_robot_count: 2 })}
      />,
    );
    expect(container.textContent).toContain("NONE PUBLISHED");
    expect(container.textContent).toContain("2 TRACKED · 0 PUBLISHED");
  });

  it("labels the country as headquarters and keeps an unresolved one UNKNOWN", () => {
    const { container } = render(<ManufacturerCard manufacturer={item({ country: null })} />);
    const text = container.textContent ?? "";
    expect(text).toContain("HQ");
    expect(text).toContain("UNKNOWN");
    expect(text).not.toContain("REGION");
  });
});
