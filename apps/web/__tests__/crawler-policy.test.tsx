/**
 * /crawler-policy (docs/16 §13, Gate R). The page must state purpose, the exact
 * user agent, the request rate, robots.txt handling and a working opt-out, and
 * must never show an invented contact address.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import CrawlerPolicyPage from "@/app/crawler-policy/page";
import { CRAWLER_CONTACT_URL, CRAWLER_USER_AGENT } from "@/lib/crawler-policy";

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

  it("points site owners to the contact form, not an email address", () => {
    const { container } = render(<CrawlerPolicyPage />);
    const link = screen.getByRole("link", { name: CRAWLER_CONTACT_URL });
    expect(link.getAttribute("href")).toBe("https://humanoidonline.com/contact");
    const text = container.textContent ?? "";
    for (const use of [
      "ask questions about the crawler",
      "request a reduced crawl frequency",
      "report a problem caused by the crawler",
      "request that your site be excluded",
    ]) {
      expect(text).toContain(use);
    }
    expect(text).not.toContain("will be published on this page before");
    expect(container.querySelectorAll('a[href^="mailto:"]')).toHaveLength(0);
  });
});
