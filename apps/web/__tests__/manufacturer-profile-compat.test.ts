/**
 * Manufacturer detail must render BOTH API response shapes.
 *
 * The web app and the API deploy independently. PR #60's Netlify preview — the
 * new page against the previous production API — returned HTTP 500 on
 * /manufacturers/{slug} because the page read `.length` on fields that API does
 * not send. These tests pin the normalisation that replaced those reads: the
 * previous shape yields explicit "not provided" states and never invented
 * values; the current shape passes through untouched.
 */
import { describe, expect, it } from "vitest";

import { manufacturerProfileView } from "../lib/manufacturer-profile";
import type { ManufacturerDetail } from "../lib/types";

/** Exactly the fields `ManufacturerDetail` had on origin/main @ b807eab. */
const PREVIOUS_API_RESPONSE = {
  id: "00000000-0000-0000-0000-000000000001",
  slug: "figure-ai",
  name: "Figure",
  legal_name: "Figure AI Inc.",
  country: "US",
  website_url: "https://www.figure.ai",
  founded_year: 2022,
  description: "US manufacturer of general-purpose humanoids.",
  commercial_model: "Direct commercial deployments with enterprise partners.",
  deployment_status: "COMMERCIAL",
  is_public_company: false,
  ticker: null,
  robots: [
    { slug: "figure-02", name: "Figure 02", commercial_status: "DISCONTINUED", primary_image: null },
  ],
  providers: [],
  deployments: [],
} as unknown as ManufacturerDetail;

const CURRENT_API_RESPONSE: ManufacturerDetail = {
  ...PREVIOUS_API_RESPONSE,
  headquarters_city: "San Jose, California",
  incorporation: null,
  operating_locations: [],
  target_markets: ["manufacturing", "logistics"],
  deployment_note: "Figure 02 worked in an 11-month deployment at BMW.",
  is_public_company: null,
  parent_company: "Group Co",
  parent_listing: "NYSE: GRP",
  parent_relationship: "Controlling shareholder",
  tracked_robot_count: 3,
  published_robot_count: 1,
  sources: [
    {
      claim_fields: ["headquarters_city"],
      source_type: "MANUFACTURER_SITE",
      source_title: "Figure — Careers",
      source_url: "https://www.figure.ai/careers",
      published_at: null,
      observed_at: "2026-09-13T00:00:00Z",
      verified_at: null,
      confidence: "HIGH",
      retrieval: "AGENT_ASSISTED_RESEARCH",
    },
  ],
};

describe("previous API response (no 0013 fields)", () => {
  const view = manufacturerProfileView(PREVIOUS_API_RESPONSE);

  it("marks every absent list and source set as not provided, not empty", () => {
    expect(view.operatingLocations).toBeNull();
    expect(view.targetMarkets).toBeNull();
    expect(view.sources).toBeNull();
  });

  it("invents no location, ownership or deployment facts", () => {
    expect(view.headquartersCity).toBeNull();
    expect(view.incorporation).toBeNull();
    expect(view.deploymentNote).toBeNull();
    expect(view.parentCompany).toBeNull();
    expect(view.parentListing).toBeNull();
    expect(view.parentRelationship).toBeNull();
  });

  it("derives the published count from the published robots list; tracked stays unknown", () => {
    expect(view.publishedModelCount).toBe(1);
    expect(view.trackedModelCount).toBeNull();
  });

  it("keeps the listing status exactly as that API sent it", () => {
    expect(view.isPublicCompany).toBe(false);
  });

  it("survives a response with no robots list at all", () => {
    const bare = { ...PREVIOUS_API_RESPONSE, robots: undefined } as unknown as ManufacturerDetail;
    expect(manufacturerProfileView(bare).publishedModelCount).toBe(0);
  });
});

describe("current API response", () => {
  const view = manufacturerProfileView(CURRENT_API_RESPONSE);

  it("passes provided values through unchanged", () => {
    expect(view.headquartersCity).toBe("San Jose, California");
    expect(view.targetMarkets).toEqual(["manufacturing", "logistics"]);
    expect(view.parentCompany).toBe("Group Co");
    expect(view.parentListing).toBe("NYSE: GRP");
    expect(view.trackedModelCount).toBe(3);
    expect(view.publishedModelCount).toBe(1);
    expect(view.sources).toHaveLength(1);
  });

  it("keeps a provided empty list distinct from an absent one", () => {
    expect(view.operatingLocations).toEqual([]);
  });

  it("keeps an unknown listing status unknown", () => {
    expect(view.isPublicCompany).toBeNull();
  });

  it("gives a source without claim_fields an empty claim list", () => {
    const partial = {
      ...CURRENT_API_RESPONSE,
      sources: [{ ...CURRENT_API_RESPONSE.sources![0], claim_fields: undefined }],
    } as unknown as ManufacturerDetail;
    expect(manufacturerProfileView(partial).sources?.[0].claim_fields).toEqual([]);
  });
});
