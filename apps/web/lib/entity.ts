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

export interface EntityProfile {
  name: string;
  description: string;
  parentOrganization: { name: string; url: string };
  founder: EntityFounder | null;
  /** ISO date or year, e.g. "2025". */
  foundingDate: string | null;
  /** Free-text headquarters location, e.g. "Prague, Czech Republic". */
  headquarters: string | null;
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
  // Not yet confirmed for publication — omitted until set.
  founder: null,
  foundingDate: null,
  headquarters: null,
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
  if (present(entity.headquarters)) {
    organization.location = { "@type": "Place", name: entity.headquarters };
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
      worksFor: { "@id": orgId },
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
  if (present(entity.foundingDate)) facts.push({ label: "Founded", value: entity.foundingDate });
  if (present(entity.headquarters)) facts.push({ label: "Headquarters", value: entity.headquarters });
  if (present(entity.contactEmail)) {
    facts.push({ label: "Contact", value: entity.contactEmail, href: `mailto:${entity.contactEmail}` });
  }
  return facts;
}
