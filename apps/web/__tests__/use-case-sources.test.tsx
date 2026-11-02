/**
 * DR-C2 — /use-cases/[slug] renders the use case's evidence as a "Sources" list, with the
 * same row markup as the manufacturer page's company sources (components/SourceRow).
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { SourceRow } from "../components/SourceRow";
import type { ManufacturerSource, UseCaseDetail } from "../lib/types";

const findUseCase = vi.fn();
vi.mock("@/lib/api-client", () => ({ findUseCase: (slug: string) => findUseCase(slug) }));

import UseCaseDetailPage from "../app/use-cases/[slug]/page";

const source = (over: Partial<ManufacturerSource> = {}): ManufacturerSource => ({
  claim_fields: ["description"],
  source_type: "PRESS_RELEASE",
  source_title: "Agility and GXO sign multi-year agreement",
  source_url: "https://example.test/gxo",
  published_at: "2024-06-27",
  observed_at: "2026-11-02T00:00:00Z",
  verified_at: null,
  confidence: "HIGH",
  retrieval: "AGENT_ASSISTED_RESEARCH",
  ...over,
});

const makeUseCase = (over: Partial<UseCaseDetail> = {}): UseCaseDetail => ({
  id: "uc-1",
  slug: "warehouse-logistics",
  name: "Warehouse & Logistics",
  description: "Text.",
  suitable_robots: [],
  ...over,
});

async function renderPage(u: UseCaseDetail) {
  findUseCase.mockResolvedValue(u);
  const ui = await UseCaseDetailPage({ params: Promise.resolve({ slug: u.slug }) });
  return render(ui);
}

beforeAll(() => {
  process.env.NEXT_PUBLIC_SITE_URL = "https://usecases.test.invalid";
});
beforeEach(() => findUseCase.mockReset());
afterEach(cleanup);

describe("use-case page — Sources", () => {
  it("lists each source with its link, supported fields, type, confidence and verification", async () => {
    const { container } = await renderPage(
      makeUseCase({
        sources: [
          source(),
          source({
            source_title: "Spot product page",
            source_url: "https://example.test/spot",
            claim_fields: ["description", "key_limitations"],
            source_type: "MANUFACTURER_SITE",
            verified_at: "2026-11-03T00:00:00Z",
            retrieval: null,
          }),
        ],
      }),
    );
    expect(screen.getByRole("heading", { name: "Sources" })).toBeTruthy();
    const section = container.querySelector("#sources")!;
    expect(section.textContent).toContain("2 SOURCES");
    expect(section.querySelectorAll(".evrow")).toHaveLength(2);

    const link = screen.getByRole("link", { name: /Agility and GXO/ });
    expect(link.getAttribute("href")).toBe("https://example.test/gxo");
    expect(link.getAttribute("rel")).toContain("noopener");
    const text = section.textContent ?? "";
    expect(text).toContain("Supports: description");
    expect(text).toContain("Supports: description, key limitations");
    expect(text).toContain("Agent-assisted research · not human-verified");
    expect(text).toContain("VERIFIED");
  });

  it("renders no Sources block when there are none, or the API predates the field", async () => {
    for (const sources of [[], undefined, null]) {
      const { container } = await renderPage(makeUseCase({ sources }));
      expect(container.querySelector("#sources")).toBeNull();
      expect(screen.queryByRole("heading", { name: "Sources" })).toBeNull();
      cleanup();
    }
  });
});

describe("SourceRow — use-case fields", () => {
  it("labels the use-case text fields and falls back to the raw field name", () => {
    const { container } = render(
      <SourceRow
        source={source({ claim_fields: ["typical_requirements", "typical_tasks", "mystery"] })}
      />,
    );
    expect(container.textContent).toContain(
      "Supports: typical requirements, typical tasks, mystery",
    );
  });

  it("says so when a source names no field", () => {
    const { container } = render(<SourceRow source={source({ claim_fields: [] })} />);
    expect(container.textContent).toContain("No field claim recorded");
  });
});
