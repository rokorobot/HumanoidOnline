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

test("llms.txt is canonical-only text with the UNKNOWN semantics", async ({ request }) => {
  const res = await request.get("/llms.txt");
  expect(res.ok()).toBeTruthy();
  expect(res.headers()["content-type"]).toContain("text/plain");
  const body = await res.text();
  expect(body).toContain("# HumanoidOnline");
  expect(body).toContain("UNKNOWN is not 0");
  expect(body).toContain("/robots/unitree-g1");
  // Canonical-only surface: no discovery-layer leakage.
  expect(body.toLowerCase()).not.toContain("candidate");
});
