// /crawler-policy — docs/16 §13 / Gate R. The URL in our crawler's user agent
// resolves here, and must explain purpose, identity, rate, robots.txt, contact
// and opt-out BEFORE the crawler fetches any product page.
//
// Informational only. Nothing on this page changes crawler behaviour: robots.txt
// is enforced in code (apps/api/app/services/discovery/robots.py), and every
// source still needs the owner's own terms review and explicit enablement.
//
// The figures come from lib/crawler-policy.ts, which mirrors the crawler's code
// constants; the API test tests/test_crawler_policy_page.py guards the parity.
//
// Contact goes through the public /contact form (Netlify Forms); no email
// address is published here.
import type { Metadata } from "next";

import { SectionIndex } from "@/components/SectionIndex";
import { SiteNav } from "@/components/SiteNav";
import { SystemHeader } from "@/components/SystemHeader";
import {
  CRAWLER_CONTACT_URL,
  CRAWLER_MIN_INTERVAL_SECONDS as MIN_INTERVAL_SECONDS,
  CRAWLER_PAGES_PER_RUN as PAGES_PER_RUN,
  CRAWLER_PRODUCT_TOKEN as PRODUCT_TOKEN,
  CRAWLER_USER_AGENT as USER_AGENT,
} from "@/lib/crawler-policy";
import { absoluteUrl } from "@/lib/site";

export function generateMetadata(): Metadata {
  return {
    title: "Crawler policy",
    description:
      "How HumanoidOnlineMarketBot observes public humanoid-robot product information: purpose, identity, request rate, robots.txt, contact and opt-out.",
    alternates: { canonical: absoluteUrl("/crawler-policy") },
  };
}

const EXCLUDE_ALL = `User-agent: ${PRODUCT_TOKEN}
Disallow: /`;

const SLOW_DOWN = `User-agent: ${PRODUCT_TOKEN}
Crawl-delay: 30`;

export default function CrawlerPolicyPage() {
  return (
    <>
      <SystemHeader title="CRAWLER POLICY / HUMANOIDONLINEMARKETBOT" />
      <div className="wrap">
        <SiteNav active={null} />
        <div className="pagebar">
          <div>
            <SectionIndex>CRAWLER POLICY</SectionIndex>
            <h1>HumanoidOnlineMarketBot</h1>
          </div>
        </div>

        <article className="prose" style={{ maxWidth: "72ch", marginBottom: "var(--ho-sp-8)" }}>
          <h2>What it is</h2>
          <p>
            HumanoidOnline operates an automated market-observation crawler, HumanoidOnlineMarketBot.
            Its purpose is to maintain evidence-backed information about humanoid robotics products
            and their commercial availability: which robots exist, their published specifications,
            prices and whether they can be ordered, together with the source each fact came from.
          </p>
          <p>
            Every value it reads is recorded as an unverified observation with its source page and a
            short supporting excerpt. Nothing it reads is published on HumanoidOnline until a person
            has reviewed it.
          </p>

          <h2>How to recognise it</h2>
          <p>Every request carries exactly this user agent, and never a browser&apos;s:</p>
          <pre>
            <code>{USER_AGENT}</code>
          </pre>
          <p>
            The robots.txt product token is <code>{PRODUCT_TOKEN}</code>.
          </p>

          <h2>Request rate</h2>
          <ul>
            <li>
              One request at a time per site, at least {MIN_INTERVAL_SECONDS} seconds apart. If your
              robots.txt sets a longer <code>Crawl-delay</code>, the longer delay is used.
            </li>
            <li>
              At most {PAGES_PER_RUN} product or announcement pages per site in one run, plus the few
              fixed listing pages they are found on. Links are followed one level only.
            </li>
            <li>
              Runs are started manually by a named member of our team. Unchanged pages are requested
              conditionally (<code>If-None-Match</code> / <code>If-Modified-Since</code>).
            </li>
            <li>
              Retries are limited to two, only after network errors or server errors (5xx).
            </li>
          </ul>

          <h2>robots.txt is respected</h2>
          <p>
            robots.txt is read at the start of every run and checked for every page and every redirect
            before it is requested. If robots.txt disallows a page, that page is not requested. If it
            disallows our crawler, the run stops and the site is disabled until a person reviews it
            again. A 401 or 403 on robots.txt is treated as a complete disallow. A 401, 403 or 429 on
            any page stops the run.
          </p>

          <h2>What it does not do</h2>
          <ul>
            <li>It does not run JavaScript, use a headless browser, log in, or solve CAPTCHAs.</li>
            <li>It does not try to get around access controls, rate limits or blocks.</li>
            <li>
              It does not keep copies of your pages. It keeps hashes, short excerpts (at most 1,000
              characters) as evidence, and links to images, not the images themselves.
            </li>
          </ul>

          <h2>Opting out or slowing it down</h2>
          <p>To exclude HumanoidOnlineMarketBot from your whole site, add to your robots.txt:</p>
          <pre>
            <code>{EXCLUDE_ALL}</code>
          </pre>
          <p>To make it visit less often, set a longer crawl delay (in seconds):</p>
          <pre>
            <code>{SLOW_DOWN}</code>
          </pre>
          <p>
            Both take effect from the next run, because robots.txt is re-read every time. You can also
            disallow only some paths.
          </p>

          <h2>Contact</h2>
          <p>
            Site owners can reach us through the contact form at{" "}
            <a href={CRAWLER_CONTACT_URL}>{CRAWLER_CONTACT_URL}</a>. Choose &ldquo;Crawler /
            robots&rdquo; or &ldquo;Crawler opt-out / rate-limit request&rdquo; and include your
            site&apos;s domain. Use it to:
          </p>
          <ul>
            <li>ask questions about the crawler;</li>
            <li>request a reduced crawl frequency;</li>
            <li>report a problem caused by the crawler;</li>
            <li>request that your site be excluded.</li>
          </ul>
          <p>
            An exclusion or rate request is applied to our crawler configuration for your site.
            Your robots.txt rules are honoured whether or not you contact us.
          </p>
        </article>
      </div>
    </>
  );
}
