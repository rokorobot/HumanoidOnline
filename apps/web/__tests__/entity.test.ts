import { beforeAll, describe, expect, it } from "vitest";

import { ENTITY, buildAboutJsonLd, entityFacts, type EntityProfile } from "@/lib/entity";

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

const CONFIRMED: EntityProfile = {
  ...ENTITY,
  founder: {
    name: "Jane Founder",
    jobTitle: "Founder",
    sameAs: ["https://www.linkedin.com/in/jane-founder", ""],
  },
  foundingDate: "2025",
  headquarters: "Somewhere, Earth",
  contactEmail: "hello@example.invalid",
  sameAs: ["https://x.com/humanoidonline", "  "],
};

describe("About JSON-LD — default (unconfirmed corporate facts)", () => {
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

  it("omits every unconfirmed field — never a placeholder, empty string or empty list", () => {
    const g = graphOf();
    const org = node(g, "Organization")!;
    for (const key of ["founder", "foundingDate", "location", "email", "contactPoint", "sameAs"]) {
      expect(org, key).not.toHaveProperty(key);
    }
    expect(node(g, "Person")).toBeUndefined();
    expect(JSON.stringify(g)).not.toMatch(/TODO|placeholder|\[URL\]|confirm/i);
  });

  it("visible facts carry only confirmed rows", () => {
    const labels = entityFacts().map((f) => f.label);
    expect(labels).toEqual(["Name", "Type", "A project of"]);
  });
});

describe("About JSON-LD — confirmed corporate facts", () => {
  it("adds founder Person, foundingDate, location, contact and sameAs, dropping blank URLs", () => {
    const g = graphOf(CONFIRMED);
    const org = node(g, "Organization")!;
    const person = node(g, "Person")!;

    expect(org.founder).toEqual({ "@id": `${ORIGIN}/about#founder` });
    expect(org.foundingDate).toBe("2025");
    expect(org.location).toEqual({ "@type": "Place", name: "Somewhere, Earth" });
    expect(org.email).toBe("hello@example.invalid");
    expect(org.sameAs).toEqual(["https://x.com/humanoidonline"]);

    expect(person["@id"]).toBe(`${ORIGIN}/about#founder`);
    expect(person.name).toBe("Jane Founder");
    expect(person.jobTitle).toBe("Founder");
    expect(person.worksFor).toEqual({ "@id": `${ORIGIN}/#organization` });
    expect(person.sameAs).toEqual(["https://www.linkedin.com/in/jane-founder"]);
  });

  it("visible facts and JSON-LD agree on the confirmed fields (parity)", () => {
    const facts = Object.fromEntries(entityFacts(CONFIRMED).map((f) => [f.label, f.value]));
    const org = node(graphOf(CONFIRMED), "Organization")!;
    expect(facts.Founder).toBe("Jane Founder");
    expect(facts.Founded).toBe(org.foundingDate);
    expect(facts.Headquarters).toBe((org.location as Node).name);
    expect(facts.Contact).toBe(org.email);
  });
});
