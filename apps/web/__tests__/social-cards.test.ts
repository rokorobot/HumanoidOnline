/**
 * SOCIAL-01 — social sharing cards.
 *
 * Pins the root metadata that makes a shared link render a large card, and the
 * two ways it could quietly go wrong: a card image resolved against the wrong
 * origin, and every route advertising the homepage's title.
 */
import { beforeAll, describe, expect, it } from "vitest";

import { generateMetadata } from "@/app/layout";
import { alt, contentType, size } from "@/app/opengraph-image";

const ORIGIN = "https://social.test.invalid";

beforeAll(() => {
  process.env.NEXT_PUBLIC_SITE_URL = ORIGIN;
});

describe("SOCIAL-01 — root social metadata", () => {
  it("requests the large-image card", () => {
    expect(generateMetadata().twitter).toMatchObject({ card: "summary_large_image" });
  });

  it("resolves card URLs against the canonical origin", () => {
    expect(generateMetadata().metadataBase?.origin).toBe(ORIGIN);
  });

  it("names the site and leaves title/description to each route", () => {
    const { openGraph, twitter } = generateMetadata();
    expect(openGraph).toMatchObject({ type: "website", siteName: "HumanoidOnline" });
    expect(openGraph).not.toHaveProperty("title");
    expect(openGraph).not.toHaveProperty("description");
    expect(twitter).not.toHaveProperty("title");
    expect(twitter).not.toHaveProperty("description");
  });
});

describe("SOCIAL-01 — card image", () => {
  it("is a 1200x630 PNG with alt text", () => {
    expect(size).toEqual({ width: 1200, height: 630 });
    expect(contentType).toBe("image/png");
    expect(alt).toContain("HumanoidOnline");
  });
});
