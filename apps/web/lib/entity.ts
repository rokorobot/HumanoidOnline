// About page — the canonical entity definition of HumanoidOnline itself.
//
// One source for both the visible key-facts table on /about and the
// Organization / Person / AboutPage JSON-LD, so the two cannot drift (the same
// parity rule AGENT-01.2 applies to robot pages).
//
// Unknown stays unknown (AGENTS.md rule 6): corporate facts that have not been
// confirmed for publication are `null` / empty here. A null field is OMITTED
// from both the visible table and the JSON-LD — never rendered as a
// placeholder, never guessed. Fill a field in only once it is confirmed.
import { absoluteUrl, siteUrl } from "@/lib/site";

export interface EntityFounder {
  name: string;
  /** Public title / role, e.g. "Founder". */
  jobTitle: string | null;
  /** Public profile URLs (LinkedIn, X, GitHub, ...). */
  sameAs: string[];
}

/** Confirmed headquarters locality — a city and country, never a street address. */
export interface EntityHeadquarters {
  locality: string;
  country: string;
  /** ISO 3166-1 alpha-2 code of `country`. */
  countryCode: string;
}

export interface EntityProfile {
  name: string;
  description: string;
  parentOrganization: { name: string; url: string };
  founder: EntityFounder | null;
  /** ISO 8601 date at the confirmed precision: "YYYY", "YYYY-MM" or "YYYY-MM-DD". */
  foundingDate: string | null;
  headquarters: EntityHeadquarters | null;
  contactEmail: string | null;
  /** Official HumanoidOnline profiles (LinkedIn, X, ...). */
  sameAs: string[];
}

export const ENTITY: EntityProfile = {
  name: "HumanoidOnline",
  description:
    "HumanoidOnline is a humanoid-robot market intelligence platform that helps " +
    "companies, operators, researchers and buyers compare humanoid robots by " +
    "capabilities, commercial availability, pricing and real-world deployment evidence.",
  parentOrganization: { name: "Humanoid.Company", url: "https://humanoid.company/" },
  // Confirmed. The founder's title, biography and profiles are NOT confirmed,
  // so they stay empty rather than guessed.
  founder: { name: "Robert Konecny", jobTitle: null, sameAs: [] },
  foundingDate: "2026-08",
  headquarters: { locality: "Prague", country: "Czech Republic", countryCode: "CZ" },
  // Not yet confirmed for publication — omitted until set. Do not publish an
  // address before its mailbox exists.
  contactEmail: null,
  sameAs: [],
};

export const ENTITY_TYPE_LABEL = "Humanoid-robot market intelligence platform";

export const ENTITY_PRINCIPLE =
  "Maturity, obtainability and evidence are different facts. Unknown stays unknown.";

export const ENTITY_KNOWS_ABOUT = [
  "Humanoid robots",
  "Humanoid robot pricing",
  "Humanoid robot commercial availability",
  "Humanoid robot deployments",
  "Robotics-as-a-Service",
];

function present(value: string | null | undefined): value is string {
  return typeof value === "string" && value.trim() !== "";
}

function nonEmpty(urls: string[]): string[] {
  return urls.filter(present);
}

const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

/**
 * Human-readable form of an ISO founding date at its own precision:
 * "2026" -> "2026", "2026-08" -> "August 2026", "2026-08-05" -> "5 August 2026".
 * Never adds precision the source does not have; an unparseable value is shown
 * as-is rather than reinterpreted.
 */
export function formatFoundingDate(iso: string): string {
  const m = /^(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?$/.exec(iso.trim());
  if (!m) return iso;
  const [, year, month, day] = m;
  if (!month) return year;
  const name = MONTHS[Number(month) - 1];
  if (!name) return iso;
  return day ? `${Number(day)} ${name} ${year}` : `${name} ${year}`;
}

/** "Prague, Czech Republic". */
export function formatHeadquarters(hq: EntityHeadquarters): string {
  return `${hq.locality}, ${hq.country}`;
}

/** Organization / Person / WebSite / AboutPage graph for /about. */
export function buildAboutJsonLd(entity: EntityProfile = ENTITY): Record<string, unknown> {
  const origin = siteUrl();
  const homeUrl = `${origin}/`;
  const aboutUrl = absoluteUrl("/about");
  const orgId = `${origin}/#organization`;
  const siteId = `${origin}/#website`;
  const founderId = `${aboutUrl}#founder`;

  const organization: Record<string, unknown> = {
    "@type": "Organization",
    "@id": orgId,
    name: entity.name,
    url: homeUrl,
    description: entity.description,
    parentOrganization: {
      "@type": "Organization",
      name: entity.parentOrganization.name,
      url: entity.parentOrganization.url,
    },
    knowsAbout: ENTITY_KNOWS_ABOUT,
  };
  if (present(entity.foundingDate)) organization.foundingDate = entity.foundingDate;
  if (entity.headquarters) {
    organization.location = {
      "@type": "Place",
      name: formatHeadquarters(entity.headquarters),
      address: {
        "@type": "PostalAddress",
        addressLocality: entity.headquarters.locality,
        addressCountry: entity.headquarters.countryCode,
      },
    };
  }
  if (present(entity.contactEmail)) {
    organization.email = entity.contactEmail;
    organization.contactPoint = {
      "@type": "ContactPoint",
      contactType: "customer support",
      email: entity.contactEmail,
    };
  }
  const orgSameAs = nonEmpty(entity.sameAs);
  if (orgSameAs.length > 0) organization.sameAs = orgSameAs;

  const graph: Array<Record<string, unknown>> = [];

  if (entity.founder && present(entity.founder.name)) {
    organization.founder = { "@id": founderId };
    const person: Record<string, unknown> = {
      "@type": "Person",
      "@id": founderId,
      name: entity.founder.name,
    };
    if (present(entity.founder.jobTitle)) person.jobTitle = entity.founder.jobTitle;
    const personSameAs = nonEmpty(entity.founder.sameAs);
    if (personSameAs.length > 0) person.sameAs = personSameAs;
    graph.push(person);
  }

  graph.unshift(
    {
      "@type": "AboutPage",
      "@id": aboutUrl,
      url: aboutUrl,
      name: `About ${entity.name}`,
      description: entity.description,
      isPartOf: { "@id": siteId },
      about: { "@id": orgId },
      mainEntity: { "@id": orgId },
    },
    {
      "@type": "WebSite",
      "@id": siteId,
      url: homeUrl,
      name: entity.name,
      publisher: { "@id": orgId },
    },
    organization,
  );

  return { "@context": "https://schema.org", "@graph": graph };
}

/** Visible key-facts rows for the confirmed corporate fields only. */
export function entityFacts(entity: EntityProfile = ENTITY): Array<{ label: string; value: string; href?: string }> {
  const facts: Array<{ label: string; value: string; href?: string }> = [
    { label: "Name", value: entity.name },
    { label: "Type", value: ENTITY_TYPE_LABEL },
    {
      label: "A project of",
      value: entity.parentOrganization.name,
      href: entity.parentOrganization.url,
    },
  ];
  if (entity.founder && present(entity.founder.name)) {
    facts.push({ label: "Founder", value: entity.founder.name });
  }
  if (present(entity.foundingDate)) {
    facts.push({ label: "Founded", value: formatFoundingDate(entity.foundingDate) });
  }
  if (entity.headquarters) {
    facts.push({ label: "Headquarters", value: formatHeadquarters(entity.headquarters) });
  }
  if (present(entity.contactEmail)) {
    facts.push({ label: "Contact", value: entity.contactEmail, href: `mailto:${entity.contactEmail}` });
  }
  return facts;
}
