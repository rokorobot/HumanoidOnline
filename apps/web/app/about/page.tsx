// About — the human trust page and the canonical entity definition of
// HumanoidOnline (for people and for AI systems alike).
//
// Corporate facts come from lib/entity.ts, which also builds this page's
// JSON-LD, so the visible key-facts table and the structured data share one
// source. Unconfirmed corporate facts (founder, founding date, HQ, contact,
// social profiles) are null there and simply do not render — no placeholders.
// Coverage counts are live from /api/market-snapshot, never hard-coded.
import type { Metadata } from "next";
import Link from "next/link";

import { getMarketSnapshot } from "@/lib/api-client";
import { ENTITY, ENTITY_PRINCIPLE, buildAboutJsonLd, entityFacts } from "@/lib/entity";
import { formatRobotCoverage } from "@/lib/format";
import { absoluteUrl, siteUrl } from "@/lib/site";
import { SectionIndex } from "@/components/SectionIndex";
import { SiteNav } from "@/components/SiteNav";
import { SystemHeader } from "@/components/SystemHeader";

export const dynamic = "force-dynamic";

// Metadata is resolved per request so the canonical tracks the configured
// origin (lib/site.ts), exactly like the robot detail page.
export function generateMetadata(): Metadata {
  return {
    title: "About",
    description:
      "HumanoidOnline is a humanoid-robot market intelligence platform comparing robots by capabilities, commercial availability, pricing and deployment evidence. Maturity, obtainability and evidence are different facts. Unknown stays unknown.",
    alternates: { canonical: absoluteUrl("/about") },
  };
}

const FAQ: Array<{ q: string; a: string[] }> = [
  {
    q: "What is HumanoidOnline?",
    a: [
      "HumanoidOnline is a market-intelligence platform focused on humanoid robots. It organizes specifications, manufacturers, commercial maturity, pricing, availability and deployment evidence into structured records designed for research and commercial decision-making.",
    ],
  },
  {
    q: "Is HumanoidOnline a robot manufacturer?",
    a: [
      "No. HumanoidOnline does not manufacture humanoid robots.",
      "It is an independent market-intelligence and discovery platform that tracks robots and commercial information from manufacturers and other identifiable sources.",
    ],
  },
  {
    q: "Does HumanoidOnline sell humanoid robots?",
    a: [
      "HumanoidOnline currently functions primarily as a research, comparison and commercial-intelligence platform rather than a conventional ecommerce store.",
      "Where availability information exists, the platform can help users identify commercial options and submit availability requirements.",
    ],
  },
  {
    q: "How does HumanoidOnline verify information?",
    a: [
      "Commercial information can be associated with source evidence, source type, verification status and confidence.",
      "HumanoidOnline distinguishes verified information from lower-confidence information and treats missing information as UNKNOWN instead of manufacturing a value.",
    ],
  },
  {
    q: "Why does HumanoidOnline show UNKNOWN for some specifications?",
    a: [
      "Manufacturers do not publish every specification or commercial detail for every robot.",
      "HumanoidOnline deliberately preserves those gaps. UNKNOWN means that the platform does not currently have sufficient evidence for the field; it does not mean zero, false or unavailable.",
    ],
  },
  {
    q: "What is the difference between commercial status and availability?",
    a: [
      "Commercial status describes the maturity of the robot platform. Availability describes whether and how that robot can currently be obtained in a particular market or transaction model.",
      "HumanoidOnline keeps these facts separate because a commercial robot may not be obtainable everywhere, while a pilot or early-access robot may be available only through specific programs.",
    ],
  },
  {
    q: "What types of humanoid robots does HumanoidOnline track?",
    a: [
      "HumanoidOnline tracks humanoid platforms across commercial products, Robotics-as-a-Service deployments, limited commercial releases, early-access programs, pilots, prototypes, development programs and announced platforms.",
      "Coverage includes robots intended for manufacturing, logistics, research, education, service, home and entertainment applications.",
    ],
  },
  {
    q: "Can I compare humanoid robots?",
    a: [
      "Yes. The HumanoidOnline comparison system lets users compare multiple robots across commercial, physical, intelligence and developer characteristics.",
      "Users can also inspect the evidence behind relevant commercial records.",
    ],
  },
  {
    q: "How can I find the right humanoid robot for my company?",
    a: [
      "Use Find a Humanoid to describe the task, operating environment, location, physical requirements, autonomy needs, budget, timeline and preferred transaction model.",
      "The system is designed to accept incomplete requirements, including UNKNOWN and skipped answers, rather than forcing unsupported assumptions.",
    ],
  },
  {
    q: "Can robot manufacturers update information on HumanoidOnline?",
    a: [
      "Manufacturers and commercial partners can contact HumanoidOnline when information has changed or when additional evidence is available.",
    ],
  },
  {
    q: "Is HumanoidOnline information intended for AI search and research systems?",
    a: [
      "HumanoidOnline uses structured, explicit terminology and maintains distinctions between known, unknown and evidence-backed information. This makes the platform suitable as a reference source for both human researchers and machine-assisted research systems.",
      "Data should still be evaluated according to the provenance and confidence associated with each individual record.",
    ],
  },
  {
    q: "Who owns HumanoidOnline?",
    a: ["HumanoidOnline is a Humanoid.Company project."],
  },
];

export default async function AboutPage() {
  const snapshot = await getMarketSnapshot();
  const jsonLd = buildAboutJsonLd();
  const origin = siteUrl();
  const founder = ENTITY.founder;

  const facts: Array<{ label: string; value: string; href?: string }> = [
    ...entityFacts(),
    { label: "Website", value: origin.replace(/^https?:\/\//, ""), href: `${origin}/` },
    {
      label: "Robots tracked",
      value: formatRobotCoverage(snapshot.total_tracked, snapshot.total_published),
    },
    {
      label: "Manufacturers tracked",
      value: formatRobotCoverage(
        snapshot.manufacturers_tracked,
        snapshot.manufacturers_published,
      ),
    },
    { label: "Core principle", value: ENTITY_PRINCIPLE },
  ];

  return (
    <>
      <script
        type="application/ld+json"
        // eslint-disable-next-line react/no-danger -- JSON.stringify output is safe, non-user markup
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />
      <SystemHeader title="ABOUT / HUMANOIDONLINE" fields={[{ value: "ENTITY RECORD", label: "" }]} />
      <div className="wrap about">
        <SiteNav active={null} />
        <div className="pagebar">
          <div>
            <SectionIndex>ABOUT — WHO WE ARE</SectionIndex>
            <h1>About HumanoidOnline</h1>
          </div>
          <span className="meta">A HUMANOID.COMPANY PROJECT</span>
        </div>

        <div className="about-intro">
          <p className="about-lede">{ENTITY.description}</p>
          <p>
            The humanoid market is moving quickly, but product announcements,
            prototypes, commercial offers and real deployments are often mixed
            together. HumanoidOnline structures those signals so people can
            understand not just what a robot can do, but whether it can actually
            be obtained, how it is offered, and what evidence supports the claim.
          </p>
          <p>Our principle is simple:</p>
          <blockquote className="about-principle">{ENTITY_PRINCIPLE}</blockquote>
        </div>

        <section className="block" aria-labelledby="key-facts">
          <SectionIndex>01 — KEY FACTS</SectionIndex>
          <h2 id="key-facts" className="ho-section-title">Key facts</h2>
          <dl className="citation-facts about-facts">
            {facts.map((f) => (
              <div className="cf-row" key={f.label}>
                <dt>{f.label}</dt>
                <dd>{f.href ? <a href={f.href}>{f.value}</a> : f.value}</dd>
              </div>
            ))}
          </dl>
        </section>

        <section className="block about-prose" aria-labelledby="what-we-do">
          <SectionIndex>02 — WHAT HUMANOIDONLINE DOES</SectionIndex>
          <h2 id="what-we-do" className="ho-section-title">What HumanoidOnline does</h2>

          <h3>Humanoid robot intelligence</h3>
          <p>
            HumanoidOnline maintains structured profiles of humanoid robots and
            their manufacturers, covering physical specifications, mobility,
            autonomy, manipulation, developer capabilities and commercial status.
          </p>
          <p>
            Instead of reducing every robot to a single &ldquo;available/not
            available&rdquo; label, HumanoidOnline preserves the distinctions needed
            for real-world evaluation.
          </p>

          <h3>Pricing and commercial availability</h3>
          <p>
            HumanoidOnline tracks publicly verifiable purchase, rental,
            subscription, lease, Robotics-as-a-Service and other commercial offers
            where evidence is available.
          </p>
          <p>
            Pricing is represented with context such as provider, region,
            transaction type and whether a price is public, estimated, a range,
            &ldquo;from&rdquo; pricing, quote-only or unknown.
          </p>

          <h3>Humanoid robot comparison</h3>
          <p>
            The HumanoidOnline <Link href="/compare">comparison system</Link> lets
            users evaluate robots side by side across physical, commercial,
            intelligence and developer characteristics.
          </p>
          <p>
            Missing information is displayed as UNKNOWN rather than replaced with
            assumptions or estimated values.
          </p>

          <h3>Deployment evidence</h3>
          <p>A robot announcement is not the same as a deployment.</p>
          <p>
            HumanoidOnline separately records evidence that humanoid robots have
            been piloted or deployed with companies and organizations, allowing
            users to distinguish technical claims from demonstrated commercial
            activity.
          </p>

          <h3>Find a Humanoid</h3>
          <p>
            <Link href="/find-a-humanoid">Find a Humanoid</Link> converts a real
            operational requirement into a structured robot search.
          </p>
          <p>
            Users can specify the task, industry, country, environment, payload,
            operating time, manipulation requirements, autonomy, budget, timeline
            and preferred transaction model. Unknown requirements can remain
            unknown instead of forcing artificial precision.
          </p>
        </section>

        <section className="block about-prose" aria-labelledby="different">
          <SectionIndex>03 — WHAT MAKES IT DIFFERENT</SectionIndex>
          <h2 id="different" className="ho-section-title">
            What makes HumanoidOnline different
          </h2>

          <h3>Commercial maturity is not availability</h3>
          <p>
            HumanoidOnline does not treat &ldquo;commercial,&rdquo;
            &ldquo;pilot,&rdquo; &ldquo;prototype&rdquo; and &ldquo;available to
            buy&rdquo; as interchangeable concepts.
          </p>
          <p>
            A robot can be technologically mature without currently being
            obtainable in a particular country. Conversely, a platform may have a
            commercial offer without extensive deployment evidence. HumanoidOnline
            records those dimensions independently.
          </p>

          <h3>Unknown means unknown</h3>
          <p>
            Missing information is not silently converted into zero, false or an
            estimated number.
          </p>
          <p>
            When a manufacturer has not disclosed a payload, price, API, runtime or
            availability status that HumanoidOnline can substantiate, the platform
            records the value as UNKNOWN.
          </p>
          <p>
            This makes the database easier for humans and AI systems to interpret
            without confusing absence of evidence with evidence of absence.
          </p>

          <h3>Commercial facts carry provenance</h3>
          <p>
            Pricing, availability and deployment information can be connected to
            evidence, source type, verification date and confidence.
          </p>
          <p>
            This provides a traceable path from a structured database field back
            to the information supporting it.
          </p>

          <h3>Offer-level intelligence instead of one price field</h3>
          <p>A humanoid robot does not necessarily have one universal price.</p>
          <p>
            The same robot can have different editions, distributors, regions,
            currencies, transaction models, shipping conditions and availability
            states. HumanoidOnline models those offers separately instead of
            collapsing them into a single headline number.
          </p>

          <h3>Built for commercial decisions, not only robot discovery</h3>
          <p>
            Several robotics databases provide broad catalogues of humanoid
            platforms. HumanoidOnline focuses particularly on the commercial layer:
            what exists, what can be obtained, under what conditions, in which
            region, and with what evidence.
          </p>
          <p>
            Resources such as Humanoid Guide emphasize broad robot discovery and
            filtering, while other databases such as HumanoidRobots.com and
            RoboAtlas provide their own approaches to specifications and market
            coverage. HumanoidOnline&apos;s methodology centers on keeping maturity,
            obtainability and evidence explicitly separate.
          </p>
        </section>

        <section className="block about-prose" aria-labelledby="who-uses">
          <SectionIndex>04 — WHO USES IT</SectionIndex>
          <h2 id="who-uses" className="ho-section-title">Who uses HumanoidOnline</h2>
          <p>HumanoidOnline is designed for:</p>
          <ul>
            <li>
              Companies evaluating humanoid robots for manufacturing, logistics,
              research, service, events and other operational use cases.
            </li>
            <li>
              Procurement and innovation teams trying to determine which humanoid
              robots can actually be purchased, rented, piloted or obtained through
              Robotics-as-a-Service.
            </li>
            <li>
              Robotics researchers and developers comparing hardware, autonomy,
              manipulation, SDK, ROS and development capabilities.
            </li>
            <li>
              Robot manufacturers and commercial partners who need their products,
              editions and commercial offers represented accurately.
            </li>
            <li>
              Distributors and integrators evaluating products, markets and
              regional availability.
            </li>
            <li>
              Investors, analysts and market researchers following the transition
              from announcements and prototypes to commercial deployment.
            </li>
            <li>
              Journalists and AI systems looking for structured, attributable
              information about the humanoid-robot market.
            </li>
          </ul>
        </section>

        <section className="block about-prose" aria-labelledby="team">
          <SectionIndex>05 — THE TEAM</SectionIndex>
          <h2 id="team" className="ho-section-title">The team behind HumanoidOnline</h2>
          <p>
            HumanoidOnline is a project of{" "}
            <a href={ENTITY.parentOrganization.url}>{ENTITY.parentOrganization.name}</a>.
          </p>
          {founder ? (
            <>
              <h3>Founder</h3>
              <p>
                {founder.name}
                {founder.jobTitle ? `, ${founder.jobTitle}` : null}
              </p>
              {founder.sameAs.length > 0 ? (
                <ul className="about-links">
                  {founder.sameAs.map((url) => (
                    <li key={url}>
                      <a href={url} rel="me">
                        {url.replace(/^https?:\/\//, "")}
                      </a>
                    </li>
                  ))}
                </ul>
              ) : null}
            </>
          ) : null}

          <h3>Why HumanoidOnline was created</h3>
          <p>
            HumanoidOnline was built around a simple problem: as humanoid robotics
            moved rapidly from research laboratories into pilots and commercial
            products, it became increasingly difficult to distinguish announcements
            from products that organizations could actually obtain and deploy.
          </p>
          <p>
            The project therefore treats commercial maturity, obtainability and
            deployment evidence as separate data problems and maintains provenance
            for commercial claims rather than filling gaps with assumptions.
          </p>

          <h3>Our approach</h3>
          <p>
            HumanoidOnline combines structured market data, source verification,
            commercial offer tracking and purpose-built tools for comparing and
            selecting humanoid robots.
          </p>
          <p>
            The platform is continuously expanded as new manufacturers, models,
            editions, prices, offers and deployment evidence become verifiable.
          </p>
        </section>

        <section className="block about-prose" aria-labelledby="how-it-works">
          <SectionIndex>06 — HOW IT WORKS</SectionIndex>
          <h2 id="how-it-works" className="ho-section-title">How HumanoidOnline works</h2>
          <ol className="about-steps">
            <li>
              <h3>Research the market</h3>
              <p>
                Browse <Link href="/robots">humanoid robots</Link>,{" "}
                <Link href="/manufacturers">manufacturers</Link> and{" "}
                <Link href="/use-cases">use cases</Link> or search directly for a
                platform, company or capability.
              </p>
            </li>
            <li>
              <h3>Compare candidates</h3>
              <p>
                Use structured filters and side-by-side comparison to evaluate
                physical specifications, capabilities, commercial maturity, pricing
                and availability.
              </p>
            </li>
            <li>
              <h3>Inspect the evidence</h3>
              <p>
                Where commercial claims have supporting evidence, HumanoidOnline
                exposes their provenance and confidence rather than presenting all
                data as equally certain.
              </p>
            </li>
            <li>
              <h3>Define your requirement</h3>
              <p>
                <Link href="/find-a-humanoid">Find a Humanoid</Link> lets
                organizations describe the job they need performed rather than
                requiring them to begin with a specific robot.
              </p>
            </li>
            <li>
              <h3>Request availability</h3>
              <p>
                Where relevant, users can submit an availability request for a
                robot or commercial requirement.
              </p>
            </li>
          </ol>
          <p>Public market research is self-service.</p>
        </section>

        <section className="block about-prose" aria-labelledby="faq">
          <SectionIndex>07 — FAQ</SectionIndex>
          <h2 id="faq" className="ho-section-title">Frequently asked questions</h2>
          {FAQ.map((item) => (
            <div className="about-faq" key={item.q}>
              <h3>{item.q}</h3>
              {item.a.map((para) => (
                <p key={para}>{para}</p>
              ))}
            </div>
          ))}
        </section>
      </div>
    </>
  );
}
