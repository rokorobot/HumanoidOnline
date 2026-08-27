import { expect, test } from "@playwright/test";

// AGENT-01 (docs/10) machine/agent surfaces, against the verified catalogue.
// Read-only projections of the canonical governed model: JSON-LD on the robot
// detail page + sitemap.xml / robots.txt / llms.txt. `unitree-g1` is a published
// catalogue robot.

test("robot detail page emits Product + Organization JSON-LD (semantic parity)", async ({ page }) => {
  await page.goto("/robots/unitree-g1");
  const ld = page.locator('script[type="application/ld+json"]');
  await expect(ld).toHaveCount(1);
  const json = JSON.parse((await ld.first().textContent()) ?? "{}");
  const graph = json["@graph"] as Array<Record<string, unknown>>;
  const product = graph.find((n) => n["@type"] === "Product")!;
  const org = graph.find((n) => n["@type"] === "Organization")!;
  expect(String(product["@id"])).toContain("/robots/unitree-g1");
  expect(String(org["@id"])).toContain("/manufacturers/");
  // Every additionalProperty carries a real value (no coerced UNKNOWN).
  for (const p of (product.additionalProperty as Array<{ value: unknown }>) ?? []) {
    expect(p.value).not.toBeNull();
  }
});

test("sitemap.xml lists published canonical entities with lastmod", async ({ request }) => {
  const res = await request.get("/sitemap.xml");
  expect(res.ok()).toBeTruthy();
  const xml = await res.text();
  expect(xml).toContain("/robots/unitree-g1");
  expect(xml).toContain("/manufacturers/");
  expect(xml).toContain("<lastmod>");
});

test("robots.txt is a deliberate inbound policy with a sitemap reference", async ({ request }) => {
  const res = await request.get("/robots.txt");
  expect(res.ok()).toBeTruthy();
  const body = await res.text();
  expect(body).toContain("Allow: /");
  expect(body.toLowerCase()).toContain("sitemap:");
});

// ---- AI Citation Layer v0.1 (docs/23) ---------------------------------------

test("CIT-D/CIT-F — CitationFacts and stable anchors are in the SERVER HTML", async ({
  request,
}) => {
  // Deliberately `request`, not `page`: this fetches the delivered HTML with no
  // browser, no JS execution and no client interaction. If the citation block
  // required hydration to appear, this assertion would fail — which is exactly
  // the CIT-D guarantee (docs/23 §24).
  const res = await request.get("/robots/unitree-g1");
  expect(res.ok()).toBeTruthy();
  const html = await res.text();

  expect(html).toContain('id="canonical-facts"');
  for (const anchor of [
    "robot-summary",
    "canonical-facts",
    "specifications",
    "commercial-status",
    "pricing",
    "availability",
    "deployments",
    "evidence",
  ]) {
    expect(html).toContain(`id="${anchor}"`);
  }
  // The facts themselves are present as text, not merely a container.
  expect(html).toContain("Record summary");
  expect(html).toContain("Commercial status");
});

test("CIT-E — the robot page emits one canonical URL matching its own identity", async ({
  request,
}) => {
  const res = await request.get("/robots/unitree-g1");
  const html = await res.text();
  const canonicals = [...html.matchAll(/<link[^>]+rel="canonical"[^>]*>/g)].map((m) => m[0]);
  expect(canonicals).toHaveLength(1);
  expect(canonicals[0]).toContain("/robots/unitree-g1");
});

test("CIT-G — OAI-SearchBot can retrieve a public robot record and the machine surfaces", async ({
  request,
}) => {
  // docs/23 §13: crawler allowance must be tested at RUNTIME, not inferred from
  // robots.ts. Sends the real declared UA against the whole citation path.
  const OAI = {
    "user-agent":
      "Mozilla/5.0 (compatible; OAI-SearchBot/1.0; +https://openai.com/searchbot)",
  };
  for (const path of ["/robots/unitree-g1", "/robots.txt", "/sitemap.xml", "/llms.txt"]) {
    const res = await request.get(path, { headers: OAI });
    expect(res.status(), `${path} must be retrievable by OAI-SearchBot`).toBe(200);
  }
});

test("CIT-H — robots.txt still declares no per-bot training policy", async ({ request }) => {
  const res = await request.get("/robots.txt");
  const body = (await res.text()).toLowerCase();
  // v0.1 must not have introduced a training-crawler split.
  for (const agent of ["gptbot", "claudebot", "google-extended", "ccbot"]) {
    expect(body).not.toContain(agent);
  }
});

test("llms.txt is canonical-only text with the UNKNOWN semantics", async ({ request }) => {
  const res = await request.get("/llms.txt");
  expect(res.ok()).toBeTruthy();
  expect(res.headers()["content-type"]).toContain("text/plain");
  const body = await res.text();
  expect(body).toContain("# HumanoidOnline");
  expect(body).toContain("UNKNOWN is not 0");
  expect(body).toContain("/robots/unitree-g1");
  // Canonical-only surface: no discovery-layer status tokens leak. (The word
  // "candidate" legitimately appears in the semantics prose that says candidates
  // are excluded — so we check for internal status leakage, not that word.)
  expect(body).not.toContain("NOT_VERIFIED");
  expect(body).not.toContain("discovery_candidate");
});
