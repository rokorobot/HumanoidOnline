import { beforeAll, describe, expect, it } from "vitest";

import {
  ENTITY,
  buildAboutJsonLd,
  entityFacts,
  formatFoundingDate,
  type EntityProfile,
} from "@/lib/entity";

const ORIGIN = "https://entity.test.invalid";

beforeAll(() => {
  process.env.NEXT_PUBLIC_SITE_URL = ORIGIN;
});

type Node = Record<string, unknown>;

function graphOf(entity?: EntityProfile): Node[] {
  const jsonld = buildAboutJsonLd(entity) as { "@context": string; "@graph": Node[] };
  expect(jsonld["@context"]).toBe("https://schema.org");
  return jsonld["@graph"];
}

function node(graph: Node[], type: string): Node | undefined {
  return graph.find((n) => n["@type"] === type);
}

// Every optional corporate fact unset — proves the omission rule independently
// of whatever the canonical ENTITY currently confirms.
const UNCONFIRMED: EntityProfile = {
  ...ENTITY,
  founder: null,
  foundingDate: null,
  headquarters: null,
  contactEmail: null,
  sameAs: [],
};

// Every optional field set, including ones the canonical ENTITY does not yet
// confirm (title, profiles, email) — proves they flow through when confirmed.
const FULLY_CONFIRMED: EntityProfile = {
  ...ENTITY,
  founder: {
    name: "Jane Founder",
    jobTitle: "Founder",
    sameAs: ["https://www.linkedin.com/in/jane-founder", ""],
  },
  foundingDate: "2025",
  headquarters: { locality: "Somewhere", country: "Earth", countryCode: "EA" },
  contactEmail: "hello@example.invalid",
  sameAs: ["https://x.com/humanoidonline", "  "],
};

describe("About JSON-LD — graph structure", () => {
  it("emits AboutPage, WebSite and Organization linked by @id on the configured origin", () => {
    const g = graphOf();
    const about = node(g, "AboutPage")!;
    const site = node(g, "WebSite")!;
    const org = node(g, "Organization")!;

    expect(about["@id"]).toBe(`${ORIGIN}/about`);
    expect(about.url).toBe(`${ORIGIN}/about`);
    expect(about.about).toEqual({ "@id": `${ORIGIN}/#organization` });
    expect(about.mainEntity).toEqual({ "@id": `${ORIGIN}/#organization` });
    expect(about.isPartOf).toEqual({ "@id": `${ORIGIN}/#website` });

    expect(site.publisher).toEqual({ "@id": `${ORIGIN}/#organization` });

    expect(org["@id"]).toBe(`${ORIGIN}/#organization`);
    expect(org.name).toBe("HumanoidOnline");
    expect(org.url).toBe(`${ORIGIN}/`);
    expect(org.parentOrganization).toEqual({
      "@type": "Organization",
      name: "Humanoid.Company",
      url: "https://humanoid.company/",
    });
  });
});

describe("About JSON-LD — canonical confirmed facts", () => {
  it("publishes founder, founding date and headquarters", () => {
    const g = graphOf();
    const org = node(g, "Organization")!;
    const person = node(g, "Person")!;

    expect(org.foundingDate).toBe("2026-08");
    expect(org.location).toEqual({
      "@type": "Place",
      name: "Prague, Czech Republic",
      address: { "@type": "PostalAddress", addressLocality: "Prague", addressCountry: "CZ" },
    });

    // Founder Person, connected through Organization.founder.
    expect(person).toBeDefined();
    expect(person.name).toBe("Robert Konecny");
    expect(org.founder).toEqual({ "@id": person["@id"] });
    expect(person["@id"]).toBe(`${ORIGIN}/about#founder`);
  });

  it("invents nothing that is not confirmed", () => {
    const g = graphOf();
    const org = node(g, "Organization")!;
    const person = node(g, "Person")!;

    // No contact details until the mailbox exists.
    expect(org).not.toHaveProperty("email");
    expect(org).not.toHaveProperty("contactPoint");
    expect(org).not.toHaveProperty("sameAs");
    // No street address, postal code or legal name.
    const address = (org.location as Node).address as Node;
    expect(Object.keys(address).sort()).toEqual(["@type", "addressCountry", "addressLocality"]);
    expect(org).not.toHaveProperty("legalName");
    // Founder: name only — no title, bio, profiles or employment claim.
    expect(Object.keys(person).sort()).toEqual(["@id", "@type", "name"]);

    const json = JSON.stringify(g);
    expect(json).not.toMatch(/@humanoidonline\.com|mailto:/i);
    expect(json).not.toMatch(/TODO|placeholder|\[URL\]|confirm/i);
  });

  it("visible key facts show the same confirmed facts", () => {
    const facts = entityFacts();
    expect(facts.map((f) => f.label)).toEqual([
      "Name",
      "Type",
      "A project of",
      "Founder",
      "Founded",
      "Headquarters",
    ]);
    const byLabel = Object.fromEntries(facts.map((f) => [f.label, f.value]));
    expect(byLabel.Founder).toBe("Robert Konecny");
    expect(byLabel.Founded).toBe("August 2026");
    expect(byLabel.Headquarters).toBe("Prague, Czech Republic");
    expect(facts.some((f) => f.href?.startsWith("mailto:"))).toBe(false);
  });

  it("visible facts and JSON-LD agree (parity from one source)", () => {
    const byLabel = Object.fromEntries(entityFacts().map((f) => [f.label, f.value]));
    const g = graphOf();
    const org = node(g, "Organization")!;
    const person = node(g, "Person")!;
    expect(byLabel.Founder).toBe(person.name);
    expect(byLabel.Founded).toBe(formatFoundingDate(org.foundingDate as string));
    expect(byLabel.Headquarters).toBe((org.location as Node).name);
  });
});

describe("About JSON-LD — unconfirmed corporate facts", () => {
  it("omits every unconfirmed field — never a placeholder, empty string or empty list", () => {
    const g = graphOf(UNCONFIRMED);
    const org = node(g, "Organization")!;
    for (const key of ["founder", "foundingDate", "location", "email", "contactPoint", "sameAs"]) {
      expect(org, key).not.toHaveProperty(key);
    }
    expect(node(g, "Person")).toBeUndefined();
    expect(JSON.stringify(g)).not.toMatch(/TODO|placeholder|\[URL\]|confirm/i);
  });

  it("visible facts carry only confirmed rows", () => {
    const labels = entityFacts(UNCONFIRMED).map((f) => f.label);
    expect(labels).toEqual(["Name", "Type", "A project of"]);
  });
});

describe("About JSON-LD — every optional field confirmed", () => {
  it("adds founder title/profiles, contact and sameAs, dropping blank URLs", () => {
    const g = graphOf(FULLY_CONFIRMED);
    const org = node(g, "Organization")!;
    const person = node(g, "Person")!;

    expect(org.founder).toEqual({ "@id": `${ORIGIN}/about#founder` });
    expect(org.foundingDate).toBe("2025");
    expect((org.location as Node).name).toBe("Somewhere, Earth");
    expect(org.email).toBe("hello@example.invalid");
    expect(org.sameAs).toEqual(["https://x.com/humanoidonline"]);

    expect(person.name).toBe("Jane Founder");
    expect(person.jobTitle).toBe("Founder");
    expect(person.sameAs).toEqual(["https://www.linkedin.com/in/jane-founder"]);
  });

  it("visible facts and JSON-LD agree on the confirmed fields (parity)", () => {
    const facts = Object.fromEntries(entityFacts(FULLY_CONFIRMED).map((f) => [f.label, f.value]));
    const org = node(graphOf(FULLY_CONFIRMED), "Organization")!;
    expect(facts.Founder).toBe("Jane Founder");
    expect(facts.Founded).toBe(org.foundingDate);
    expect(facts.Headquarters).toBe((org.location as Node).name);
    expect(facts.Contact).toBe(org.email);
  });
});

describe("formatFoundingDate", () => {
  it("renders at the source precision and never adds precision", () => {
    expect(formatFoundingDate("2026")).toBe("2026");
    expect(formatFoundingDate("2026-08")).toBe("August 2026");
    expect(formatFoundingDate("2026-08-05")).toBe("5 August 2026");
  });

  it("passes an unparseable value through unchanged", () => {
    expect(formatFoundingDate("2026-13")).toBe("2026-13");
    expect(formatFoundingDate("summer 2026")).toBe("summer 2026");
  });
});
