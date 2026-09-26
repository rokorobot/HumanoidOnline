/**
 * /crawler-policy (docs/16 §13, Gate R). The page must state purpose, the exact
 * user agent, the request rate, robots.txt handling and a working opt-out, and
 * must never show an invented contact address.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import CrawlerPolicyPage from "@/app/crawler-policy/page";
import { CRAWLER_USER_AGENT } from "@/lib/crawler-policy";
import { ENTITY } from "@/lib/entity";

describe("/crawler-policy", () => {
  afterEach(cleanup);

  it("states identity, purpose, rate, robots handling and opt-out", () => {
    const { container } = render(<CrawlerPolicyPage />);
    const text = container.textContent ?? "";
    expect(screen.getByRole("heading", { level: 1, name: "HumanoidOnlineMarketBot" })).toBeTruthy();
    expect(text).toContain(CRAWLER_USER_AGENT);
    expect(text).toContain("automated market-observation crawler");
    expect(text).toContain("evidence-backed information about humanoid robotics products");
    expect(text).toContain("at least 2 seconds apart");
    expect(text).toContain("At most 50 product or announcement pages");
    expect(text).toContain("robots.txt is read at the start of every run");
    expect(text).toContain("User-agent: HumanoidOnlineMarketBot\nDisallow: /");
    expect(text).toContain("Crawl-delay: 30");
  });

  it("never invents a contact address", () => {
    const { container } = render(<CrawlerPolicyPage />);
    const mailto = container.querySelectorAll('a[href^="mailto:"]');
    if (ENTITY.contactEmail) {
      expect(mailto).toHaveLength(1);
    } else {
      expect(mailto).toHaveLength(0);
      expect(container.textContent).toContain("will be published on this page before");
    }
  });
});
