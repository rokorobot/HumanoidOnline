// About — the human trust page and the canonical entity definition of
// HumanoidOnline (for people and for AI systems alike).
//
// Corporate facts come from lib/entity.ts, which also builds this page's
// JSON-LD, so the visible key-facts table and the structured data share one
// source. Unconfirmed corporate facts (e.g. contact email, social profiles,
// founder title) are null there and simply do not render — no placeholders.
// Coverage counts are live from /api/market-snapshot, never hard-coded.
//
// Visual register follows the home page (docs/07 §1: identity surfaces may be
// bold): dark hero with the key-facts readout, then numbered paper sections,
// a dark live-coverage band, and quiet, legible text blocks.
import type { Metadata } from "next";
import Link from "next/link";

import { getMarketSnapshot } from "@/lib/api-client";
import {
  ENTITY,
  ENTITY_PRINCIPLE,
  buildAboutJsonLd,
  entityFacts,
  formatFoundingDate,
  formatHeadquarters,
} from "@/lib/entity";
import { formatRobotCoverage } from "@/lib/format";
import { absoluteUrl, siteUrl } from "@/lib/site";
import { GraphicMarker } from "@/components/GraphicMarker";
import { MachineCode } from "@/components/MachineCode";
import { SectionIndex } from "@/components/SectionIndex";
import { DarkNav } from "@/components/SiteNav";
import { SystemHeader } from "@/components/SystemHeader";
import { SystemLabel } from "@/components/SystemLabel";

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

// Section content. Copy is the approved About text; the layout reuses the
// site's own grammar (dark hero + readout, numbered sections, hard-ruled
// tiles, dark snapshot band) rather than a long-form prose page.
const CAPABILITIES: Array<{ title: string; body: string[]; href?: string; cta?: string }> = [
  {
    title: "Humanoid robot intelligence",
    body: [
      "Structured profiles of humanoid robots and their manufacturers, covering physical specifications, mobility, autonomy, manipulation, developer capabilities and commercial status.",
      "Instead of reducing every robot to a single “available/not available” label, HumanoidOnline preserves the distinctions needed for real-world evaluation.",
    ],
    href: "/robots",
    cta: "Open catalogue",
  },
  {
    title: "Pricing and commercial availability",
    body: [
      "Publicly verifiable purchase, rental, subscription, lease, Robotics-as-a-Service and other commercial offers, where evidence is available.",
      "Pricing carries its context: provider, region, transaction type and whether a price is public, estimated, a range, “from” pricing, quote-only or unknown.",
    ],
  },
  {
    title: "Humanoid robot comparison",
    body: [
      "Evaluate robots side by side across physical, commercial, intelligence and developer characteristics.",
      "Missing information is displayed as UNKNOWN rather than replaced with assumptions or estimated values.",
    ],
    href: "/compare",
    cta: "Compare robots",
  },
  {
    title: "Deployment evidence",
    body: [
      "A robot announcement is not the same as a deployment.",
      "HumanoidOnline separately records evidence that humanoid robots have been piloted or deployed with companies and organizations, distinguishing technical claims from demonstrated commercial activity.",
    ],
  },
  {
    title: "Find a Humanoid",
    body: [
      "Converts a real operational requirement into a structured robot search: task, industry, country, environment, payload, operating time, manipulation, autonomy, budget, timeline and preferred transaction model.",
      "Unknown requirements can remain unknown instead of forcing artificial precision.",
    ],
    href: "/find-a-humanoid",
    cta: "Start a requirement",
  },
];

const DIFFERENTIATORS: Array<{ title: string; body: string[] }> = [
  {
    title: "Commercial maturity is not availability",
    body: [
      "HumanoidOnline does not treat “commercial,” “pilot,” “prototype” and “available to buy” as interchangeable concepts.",
      "A robot can be technologically mature without currently being obtainable in a particular country. Conversely, a platform may have a commercial offer without extensive deployment evidence. HumanoidOnline records those dimensions independently.",
    ],
  },
  {
    title: "Unknown means unknown",
    body: [
      "Missing information is not silently converted into zero, false or an estimated number. When a manufacturer has not disclosed a payload, price, API, runtime or availability status that HumanoidOnline can substantiate, the platform records the value as UNKNOWN.",
      "This makes the database easier for humans and AI systems to interpret without confusing absence of evidence with evidence of absence.",
    ],
  },
  {
    title: "Commercial facts carry provenance",
    body: [
      "Pricing, availability and deployment information can be connected to evidence, source type, verification date and confidence — a traceable path from a structured database field back to the information supporting it.",
    ],
  },
  {
    title: "Offer-level intelligence instead of one price field",
    body: [
      "A humanoid robot does not necessarily have one universal price. The same robot can have different editions, distributors, regions, currencies, transaction models, shipping conditions and availability states. HumanoidOnline models those offers separately instead of collapsing them into a single headline number.",
    ],
  },
  {
    title: "Built for commercial decisions, not only robot discovery",
    body: [
      "Several robotics databases provide broad catalogues of humanoid platforms. HumanoidOnline focuses particularly on the commercial layer: what exists, what can be obtained, under what conditions, in which region, and with what evidence.",
      "Resources such as Humanoid Guide emphasize broad robot discovery and filtering, while other databases such as HumanoidRobots.com and RoboAtlas provide their own approaches to specifications and market coverage. HumanoidOnline’s methodology centers on keeping maturity, obtainability and evidence explicitly separate.",
    ],
  },
];

const AUDIENCES: Array<{ name: string; body: string }> = [
  {
    name: "Operators",
    body: "Companies evaluating humanoid robots for manufacturing, logistics, research, service, events and other operational use cases.",
  },
  {
    name: "Procurement & innovation",
    body: "Teams determining which humanoid robots can actually be purchased, rented, piloted or obtained through Robotics-as-a-Service.",
  },
  {
    name: "Researchers & developers",
    body: "Comparing hardware, autonomy, manipulation, SDK, ROS and development capabilities.",
  },
  {
    name: "Manufacturers & partners",
    body: "Who need their products, editions and commercial offers represented accurately.",
  },
  {
    name: "Distributors & integrators",
    body: "Evaluating products, markets and regional availability.",
  },
  {
    name: "Investors & analysts",
    body: "Following the transition from announcements and prototypes to commercial deployment.",
  },
  {
    name: "Journalists & AI systems",
    body: "Looking for structured, attributable information about the humanoid-robot market.",
  },
];

const STEPS: Array<{ title: string; body: string; href?: string; cta?: string }> = [
  {
    title: "Research the market",
    body: "Browse humanoid robots, manufacturers and use cases, or search directly for a platform, company or capability.",
    href: "/robots",
    cta: "Robots",
  },
  {
    title: "Compare candidates",
    body: "Use structured filters and side-by-side comparison to evaluate specifications, capabilities, commercial maturity, pricing and availability.",
    href: "/compare",
    cta: "Compare",
  },
  {
    title: "Inspect the evidence",
    body: "Where commercial claims have supporting evidence, their provenance and confidence are exposed rather than presenting all data as equally certain.",
  },
  {
    title: "Define your requirement",
    body: "Find a Humanoid lets organizations describe the job they need performed rather than requiring them to begin with a specific robot.",
    href: "/find-a-humanoid",
    cta: "Find a Humanoid",
  },
  {
    title: "Request availability",
    body: "Where relevant, submit an availability request for a robot or commercial requirement.",
  },
];

function pad(n: number): string {
  return String(n).padStart(2, "0");
}

export default async function AboutPage() {
  const snapshot = await getMarketSnapshot();
  const jsonLd = buildAboutJsonLd();
  const origin = siteUrl();
  const founder = ENTITY.founder;
  const hq = ENTITY.headquarters;

  const facts: Array<{ label: string; value: string; href?: string }> = [
    ...entityFacts(),
    { label: "Website", value: origin.replace(/^https?:\/\//, ""), href: `${origin}/` },
    {
      label: "Robots",
      value: formatRobotCoverage(snapshot.total_tracked, snapshot.total_published),
    },
    {
      label: "Manufacturers",
      value: formatRobotCoverage(
        snapshot.manufacturers_tracked,
        snapshot.manufacturers_published,
      ),
    },
  ];

  return (
    <>
      <script
        type="application/ld+json"
        // eslint-disable-next-line react/no-danger -- JSON.stringify output is safe, non-user markup
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />
      <SystemHeader
        title="ABOUT / ENTITY RECORD"
        fields={[
          { value: snapshot.total_tracked, label: "" },
          { value: "PLATFORMS TRACKED", label: "" },
        ]}
      />

      {/* HERO (dark) — same control-room register as the home hero */}
      <div className="hero-shell ho-dark ho-scan">
        <div className="hero-inner">
          <div className="topbar">
            <div className="corner">
              <span className="ho-star">&#9733;</span>
            </div>
            <div className="seg logo">
              <Link href="/">
                <b>HUMANOIDONLINE</b>
              </Link>
            </div>
            <div className="seg mid">ABOUT / ENTITY DEFINITION</div>
            <div className="seg">
              <DarkNav active={null} />
            </div>
            <div className="corner">
              <span className="ho-star">&#9733;</span>
            </div>
          </div>

          <div className="hero-body about-hero">
            <div className="hero-side l">
              <span className="ho-vertical">ENTITY: HUMANOIDONLINE</span>
            </div>
            <div className="hero-side r">
              <span className="ho-vertical">
                A {ENTITY.parentOrganization.name.toUpperCase()} PROJECT
              </span>
            </div>

            <div className="hero-kicker">
              <SectionIndex>00 — WHO WE ARE</SectionIndex>
              <span className="ho-reg-box">&reg;</span>
            </div>

            <h1>
              About <br />
              <em>HumanoidOnline</em>
            </h1>

            <div className="subrow">
              <div className="cell about-lede">{ENTITY.description}</div>
              <div className="cell">
                Announcements, prototypes, commercial offers and real deployments
                are often mixed together. HumanoidOnline structures those signals:
                what a robot can do, whether it can actually be obtained, how it
                is offered, and what evidence supports the claim.
              </div>
              <Link className="act" href="/find-a-humanoid">
                Find a
                <br />
                Humanoid
              </Link>
            </div>

            <div className="hero-tools about-tools">
              <div>
                <p className="ho-syslabel about-principle-label">Our principle</p>
                <p className="about-principle">
                  <span>Maturity ≠ obtainability ≠ evidence.</span>
                  <span className="sig">Unknown stays unknown.</span>
                </p>
                <p className="about-principle-text">{ENTITY_PRINCIPLE}</p>
                <div className="hero-actions">
                  <Link className="btn" href="/robots">
                    <GraphicMarker /> Explore Robots
                  </Link>
                  <Link className="btn" href="/compare">
                    <GraphicMarker /> Compare
                  </Link>
                </div>
              </div>
              <div className="readout" aria-labelledby="key-facts">
                <h2 id="key-facts" className="ho-syslabel about-readout-title">
                  Key facts
                </h2>
                <dl className="about-facts">
                  {facts.map((f) => (
                    <div className="cf-row" key={f.label}>
                      <dt>{f.label}</dt>
                      <dd>{f.href ? <a href={f.href}>{f.value}</a> : f.value}</dd>
                    </div>
                  ))}
                </dl>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* 01 — WHAT IT DOES */}
      <section className="block" aria-labelledby="what-we-do">
        <div className="wrap">
          <div className="block-head">
            <div>
              <SectionIndex>01 — WHAT HUMANOIDONLINE DOES</SectionIndex>
              <h2 id="what-we-do" className="ho-section-title">What it does</h2>
            </div>
            <SystemLabel>{CAPABILITIES.length} CAPABILITIES</SystemLabel>
          </div>
          <div className="about-grid">
            {CAPABILITIES.map((c, i) => (
              <article className="about-card" key={c.title}>
                <SystemLabel>{pad(i + 1)}</SystemLabel>
                <h3>{c.title}</h3>
                {c.body.map((p) => (
                  <p key={p}>{p}</p>
                ))}
                {c.href ? (
                  <MachineCode href={c.href}>{`${c.cta?.toUpperCase()} →`}</MachineCode>
                ) : null}
              </article>
            ))}
          </div>
        </div>
      </section>

      {/* 02 — WHAT MAKES IT DIFFERENT (stepped list, big index numerals) */}
      <section className="block" aria-labelledby="different">
        <div className="wrap">
          <div className="block-head">
            <div>
              <SectionIndex>02 — WHAT MAKES IT DIFFERENT</SectionIndex>
              <h2 id="different" className="ho-section-title">
                What makes HumanoidOnline different
              </h2>
            </div>
            <SystemLabel>METHODOLOGY</SystemLabel>
          </div>
          <ol className="about-rows">
            {DIFFERENTIATORS.map((d, i) => (
              <li className="about-row" key={d.title}>
                <span className="n" aria-hidden="true">
                  {pad(i + 1)}
                </span>
                <h3>{d.title}</h3>
                <div className="txt">
                  {d.body.map((p) => (
                    <p key={p}>{p}</p>
                  ))}
                </div>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* 03 — COVERAGE (dark snapshot band, live numbers) */}
      <section className="snapshot ho-dark ho-scan" aria-labelledby="coverage">
        <div className="wrap">
          <SectionIndex>03 — COVERAGE</SectionIndex>
          <h2 id="coverage" className="ho-section-title about-snap-title">
            Coverage, live
          </h2>
          <div className="snap-grid">
            <Snap
              n={snapshot.total_tracked}
              label="Humanoids tracked"
              sub={`${snapshot.total_published} published profiles`}
            />
            <Snap n={snapshot.commercially_accessible} label="Commercially accessible" signal />
            <Snap n={snapshot.in_deployment_or_pilot} label="In pilot / deployment" />
            <Snap
              n={snapshot.manufacturers_tracked}
              label="Manufacturers tracked"
              sub={`${snapshot.manufacturers_published} with published profiles`}
            />
          </div>
          <p className="ho-syslabel about-snap-note">
            Live from the catalogue. The platform is continuously expanded as new
            manufacturers, models, editions, prices, offers and deployment evidence
            become verifiable.
          </p>
        </div>
      </section>

      {/* 04 — WHO USES IT */}
      <section className="block" aria-labelledby="who-uses">
        <div className="wrap">
          <div className="block-head">
            <div>
              <SectionIndex>04 — WHO USES IT</SectionIndex>
              <h2 id="who-uses" className="ho-section-title">Who uses HumanoidOnline</h2>
            </div>
            <SystemLabel>{AUDIENCES.length} AUDIENCES</SystemLabel>
          </div>
          <ul className="apps about-audiences">
            {AUDIENCES.map((a, i) => (
              <li className="app" key={a.name}>
                <SystemLabel>{pad(i + 1)}</SystemLabel>
                <span className="name">{a.name}</span>
                <span className="about-aud-body">{a.body}</span>
              </li>
            ))}
            <li className="app about-aud-cta">
              <SystemLabel>→</SystemLabel>
              <Link className="name" href="/find-a-humanoid">
                Find a Humanoid
              </Link>
            </li>
          </ul>
        </div>
      </section>

      {/* 05 — THE TEAM */}
      <section className="block" aria-labelledby="team">
        <div className="wrap">
          <div className="block-head">
            <div>
              <SectionIndex>05 — THE TEAM</SectionIndex>
              <h2 id="team" className="ho-section-title">The team behind HumanoidOnline</h2>
            </div>
            <SystemLabel>
              A{" "}
              <a className="about-inline" href={ENTITY.parentOrganization.url}>
                {ENTITY.parentOrganization.name.toUpperCase()}
              </a>{" "}
              PROJECT
            </SystemLabel>
          </div>
          <div className="two-col">
            <div className="about-team-card">
              {founder ? (
                <>
                  <SystemLabel>FOUNDER</SystemLabel>
                  <h3 className="about-founder">
                    {founder.name}
                    {founder.jobTitle ? `, ${founder.jobTitle}` : null}
                  </h3>
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
              <div className="about-team-meta">
                {ENTITY.foundingDate ? (
                  <Leader k="FOUNDED" v={formatFoundingDate(ENTITY.foundingDate)} />
                ) : null}
                {hq ? <Leader k="HQ" v={formatHeadquarters(hq)} /> : null}
                <Leader k="PROJECT OF" v={ENTITY.parentOrganization.name} />
              </div>
            </div>
            <div className="about-prose">
              <h3>Why HumanoidOnline was created</h3>
              <p>
                HumanoidOnline was built around a simple problem: as humanoid
                robotics moved rapidly from research laboratories into pilots and
                commercial products, it became increasingly difficult to
                distinguish announcements from products that organizations could
                actually obtain and deploy.
              </p>
              <p>
                The project therefore treats commercial maturity, obtainability and
                deployment evidence as separate data problems and maintains
                provenance for commercial claims rather than filling gaps with
                assumptions.
              </p>
              <h3>Our approach</h3>
              <p>
                HumanoidOnline combines structured market data, source verification,
                commercial offer tracking and purpose-built tools for comparing and
                selecting humanoid robots.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* 06 — HOW IT WORKS */}
      <section className="block" aria-labelledby="how-it-works">
        <div className="wrap">
          <div className="block-head">
            <div>
              <SectionIndex>06 — HOW IT WORKS</SectionIndex>
              <h2 id="how-it-works" className="ho-section-title">How HumanoidOnline works</h2>
            </div>
            <SystemLabel>PUBLIC MARKET RESEARCH IS SELF-SERVICE</SystemLabel>
          </div>
          <ol className="about-flow">
            {STEPS.map((s, i) => (
              <li key={s.title}>
                <span className="n" aria-hidden="true">
                  {pad(i + 1)}
                </span>
                <h3>{s.title}</h3>
                <p>{s.body}</p>
                {s.href ? (
                  <MachineCode href={s.href}>{`${s.cta?.toUpperCase()} →`}</MachineCode>
                ) : null}
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* 07 — FAQ */}
      <section className="block" aria-labelledby="faq">
        <div className="wrap">
          <div className="block-head">
            <div>
              <SectionIndex>07 — FAQ</SectionIndex>
              <h2 id="faq" className="ho-section-title">Frequently asked questions</h2>
            </div>
            <SystemLabel>{FAQ.length} QUESTIONS</SystemLabel>
          </div>
          <div className="about-faq">
            {FAQ.map((item, i) => (
              <div className="about-faq-item" key={item.q}>
                <span className="q ho-syslabel" aria-hidden="true">
                  Q.{pad(i + 1)}
                </span>
                <div>
                  <h3>{item.q}</h3>
                  {item.a.map((para) => (
                    <p key={para}>{para}</p>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>
    </>
  );
}

function Leader({ k, v }: { k: string; v: string }) {
  return (
    <div className="ho-leader">
      <span>{k}</span>
      <span className="fill" />
      <span>{v}</span>
    </div>
  );
}

function Snap({
  n,
  label,
  signal,
  sub,
}: {
  n: number;
  label: string;
  signal?: boolean;
  sub?: string;
}) {
  return (
    <div className="snap">
      <div className={signal ? "num sig" : "num"}>{n}</div>
      <div className="lbl ho-syslabel">{label}</div>
      {sub ? <div className="lbl ho-syslabel">{sub}</div> : null}
    </div>
  );
}
