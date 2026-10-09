/**
 * UX-02 - catalogue discovery & comparison: query application, interpretation chips, provider
 * names, comparison continuity through the robot detail page, and visible-enum labels.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

import { CitationFacts, citationFacts } from "@/components/CitationFacts";
import { DetailComparisonLink } from "@/components/DetailComparisonLink";
import { InterpretationBar } from "@/components/InterpretationBar";
import { AvailabilityMatrix } from "@/components/AvailabilityState";
import { PriceStateCard } from "@/components/PricingState";
import { SearchBox } from "@/components/SearchBox";
import { partlyUninterpreted, resolveCatalogueQuery } from "@/lib/catalogue-query";
import { enumLabel } from "@/lib/labels";
import {
  parseSlugs,
  resolveNavTarget,
  selectionFromLocation,
  toggleSlug,
} from "@/lib/nav-selection";
import { interpretQuery, type InterpreterVocab } from "@/lib/query-interpreter";
import { providerLabel, providerNamesFrom } from "@/lib/providers";
import { countActiveFilters, toRobotListParams } from "@/lib/search-params";
import type { AvailabilityOffer, PriceDisplay, PricingOffer, RobotDetail } from "@/lib/types";

const vocab: InterpreterVocab = {
  manufacturers: [
    { slug: "unitree", name: "Unitree Robotics" },
    { slug: "agility-robotics", name: "Agility Robotics" },
  ],
  useCases: [
    { slug: "warehouse-logistics", name: "Warehouse & Logistics" },
    { slug: "research-education", name: "Research & Education" },
  ],
};

beforeEach(() => {
  push.mockClear();
  window.history.replaceState(null, "", "/");
});
afterEach(cleanup);

// ---- UX-02A: how a query becomes API parameters --------------------------------------------
describe("resolveCatalogueQuery - the URL stays the source of truth", () => {
  it("maps the interpretation to the exact API params; q becomes the residual words", () => {
    const cq = resolveCatalogueQuery({ q: "unitree g1 under 20k eur" }, vocab);
    const api = toRobotListParams(cq.effective);
    expect(api.manufacturer).toBe("unitree");
    expect(api.q).toBe("g1");
    // the price pair is inseparable and explicit; nothing converts or defaults
    expect(api.price_max).toBe(20000);
    expect(api.price_currency).toBe("EUR");
  });

  it("a number without a currency sends NO price params at all", () => {
    const api = toRobotListParams(resolveCatalogueQuery({ q: "warehouse under 20000" }, vocab).effective);
    expect(api.price_max).toBeUndefined();
    expect(api.price_currency).toBeUndefined();
    expect(api.use_case).toBe("warehouse-logistics");
  });

  it("a rental word filters OBTAINABILITY (availability offers); it is never a price or a purchase ceiling", () => {
    const api = toRobotListParams(resolveCatalogueQuery({ q: "rent" }, vocab).effective);
    expect(api.transaction_type).toEqual(["RENTAL"]);
    expect(api.price_max).toBeUndefined();
    // And the price ceiling the API applies is PURCHASE-only, exact currency, no FX; unknown prices and
    // QUOTE_ONLY have no comparable amount, so they can never match a ceiling (as 0 or otherwise).
    const root = resolve(process.cwd(), "..", "api", "app", "services", "pricing.py");
    const src = readFileSync(root, "utf8");
    expect(src).toContain('PricingOffer.transaction_type == "PURCHASE"');
    expect(src).toContain("PricingOffer.currency == price_currency.upper()");
    expect(src).toContain("amount.is_not(None), amount <= ceiling");
    expect(src).toMatch(/QUOTE_ONLY.*falls through to NULL|QUOTE_ONLY. falls through to NULL/s);
  });

  it("an explicit URL filter wins over the interpreted one and the chip says it was not applied", () => {
    const cq = resolveCatalogueQuery({ q: "unitree", manufacturer: "agility-robotics" }, vocab);
    expect(toRobotListParams(cq.effective).manufacturer).toBe("agility-robotics");
    expect(cq.overridden.has("manufacturer")).toBe(true);
    expect(cq.chips[0].status).toBe("not_applied");
    expect(cq.chips[0].note).toMatch(/already set to something else/);
    expect(partlyUninterpreted(cq)).toBe(true);
  });

  it("an explicit price wins over a different interpreted one", () => {
    const cq = resolveCatalogueQuery({ q: "under 20000 eur", price_max: "5000", price_currency: "USD" }, vocab);
    const api = toRobotListParams(cq.effective);
    expect(api.price_max).toBe(5000);
    expect(api.price_currency).toBe("USD");
    expect(cq.overridden.has("price")).toBe(true);
  });

  it("an explicit filter equal to the interpreted one is not a conflict", () => {
    const cq = resolveCatalogueQuery({ q: "unitree", manufacturer: "unitree" }, vocab);
    expect(cq.overridden.size).toBe(0);
  });

  it("no q means no interpretation and the URL params pass through untouched", () => {
    const sp = { region: "DE" };
    const cq = resolveCatalogueQuery(sp, vocab);
    expect(cq.interpretation).toBeNull();
    expect(cq.effective).toBe(sp);
  });

  it("is deterministic: the same URL always gives the same API call", () => {
    const sp = { q: "unitree research under $20000 purchase" };
    expect(resolveCatalogueQuery(sp, vocab).effective).toEqual(resolveCatalogueQuery(sp, vocab).effective);
  });

  it("flags a query that could not be fully interpreted", () => {
    expect(partlyUninterpreted(resolveCatalogueQuery({ q: "under 20000" }, vocab))).toBe(true);
    expect(partlyUninterpreted(resolveCatalogueQuery({ q: "unitree" }, vocab))).toBe(false);
    expect(partlyUninterpreted(resolveCatalogueQuery({ q: "over 5000 eur" }, vocab))).toBe(true);
  });
});

describe("active filter count - counts the constraints actually applied", () => {
  const count = (sp: Record<string, string | string[]>) =>
    countActiveFilters(resolveCatalogueQuery(sp, vocab).effective);

  it("a compound query counts each interpreted filter, not the search box as one", () => {
    // use case + purchase-price ceiling = 2 (the currency only denominates the ceiling)
    expect(count({ q: "warehouse robot under €20000" })).toBe(2);
    // manufacturer + use case + price + obtainability = 4
    expect(count({ q: "unitree research under $20000 purchase" })).toBe(4);
    // manufacturer + leftover name words (one name search) + price = 3
    expect(count({ q: "unitree g1 under 20k eur" })).toBe(3);
  });

  it("is a function of the applied constraints only, so a zero-result search reports the same count", () => {
    const cq = resolveCatalogueQuery({ q: "warehouse robot under €20000" }, vocab);
    expect(cq.chips.filter((c) => c.status === "applied")).toHaveLength(2);
    expect(countActiveFilters(cq.effective)).toBe(2);
    // an unrecognised word is still one applied name search, whatever it returns
    expect(count({ q: "waterproof" })).toBe(1);
  });

  it("does not count interpreted parts that were not applied", () => {
    expect(count({ q: "warehouse under 20000" })).toBe(1); // no currency: price not applied
    // an explicit, different use case wins; the interpreted one is not counted twice
    expect(count({ q: "warehouse", use_case: "research-education" })).toBe(1);
  });

  it("counts independently selected filters, alone and alongside a query", () => {
    expect(count({})).toBe(0);
    expect(count({ region: "DE" })).toBe(1);
    expect(count({ region: "DE", offered_in: "EU" })).toBe(2);
    expect(count({ commercial_status: ["COMMERCIAL", "PILOT"], transaction_type: ["RENTAL"] })).toBe(3);
    expect(count({ price_max: "30000", price_currency: "USD" })).toBe(1);
    expect(count({ q: "warehouse", region: "DE", commercial_status: ["COMMERCIAL", "PILOT"] })).toBe(4);
    // the same filter stated in the URL and in the query is one constraint
    expect(count({ q: "warehouse", use_case: "warehouse-logistics" })).toBe(1);
  });

  it("agrees with the number of filters sent to the API", () => {
    const api = toRobotListParams(resolveCatalogueQuery({ q: "warehouse robot under €20000" }, vocab).effective);
    expect([api.use_case, api.price_max, api.q, api.manufacturer].filter((v) => v != null)).toHaveLength(2);
  });
});

describe("SearchBox", () => {
  it("is a labelled GET form field pre-filled from the URL, sending only q", () => {
    const html = renderToStaticMarkup(<SearchBox q="unitree g1" />);
    expect(html).toContain('role="search"');
    expect(html).toContain('name="q"');
    expect(html).toContain('value="unitree g1"');
    expect(html).toContain('aria-label="Search robots"');
    expect(html).not.toMatch(/<input[^>]*type="hidden"/);
    expect(html).not.toContain("<a ");
  });
});

describe("InterpretationBar", () => {
  const interp = interpretQuery("warehouse robot under €20000", vocab);
  const bar = (over: Partial<Parameters<typeof InterpretationBar>[0]> = {}) => (
    <InterpretationBar
      text={interp.text}
      chips={interp.chips}
      base="sort=name&region=DE"
      residualUnmatched={[]}
      unsupported={[]}
      conflicts={[]}
      hasAppliedPrice
      {...over}
    />
  );

  it("shows the chips and the 'recorded purchase prices in that currency only' note", () => {
    const { container } = render(bar());
    expect(screen.getByText("Use case: Warehouse & Logistics")).toBeTruthy();
    expect(screen.getByText("Maximum purchase price: €20,000")).toBeTruthy();
    expect(container.textContent).toMatch(/recorded purchase prices in that currency only/);
    expect(container.textContent).toMatch(/not evidence that they cost more/);
  });

  it("removing a chip rewrites only q and keeps every other URL parameter; no anchors are emitted", () => {
    const { container } = render(bar());
    expect(container.querySelector("a")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Remove: Maximum purchase price: €20,000" }));
    const url = String(push.mock.calls.at(-1)?.[0]);
    const q = new URLSearchParams(url.split("?")[1]);
    expect(q.get("q")).toBe("warehouse robot");
    expect(q.get("region")).toBe("DE");
    expect(q.get("sort")).toBe("name");
  });

  it("removing the last chip drops q entirely", () => {
    const one = interpretQuery("unitree", vocab);
    render(bar({ text: one.text, chips: one.chips, base: "", hasAppliedPrice: false }));
    fireEvent.click(screen.getByRole("button", { name: /^Remove:/ }));
    expect(push).toHaveBeenCalledWith("/robots", { scroll: false });
  });

  it("a price with no currency offers explicit choices and applies none by default", () => {
    const r = interpretQuery("under 20000", vocab);
    render(bar({ text: r.text, chips: r.chips, hasAppliedPrice: false }));
    expect(screen.getByText("Maximum purchase price 20,000 — choose a currency")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "GBP" }));
    const url = String(push.mock.calls.at(-1)?.[0]);
    expect(new URLSearchParams(url.split("?")[1]).get("q")).toBe("under 20000 GBP");
  });

  it("lists words that matched nothing plainly", () => {
    const { container } = render(bar({ chips: [], residualUnmatched: ["waterproof"], hasAppliedPrice: false }));
    expect(container.textContent).toContain("Not understood: “waterproof”");
  });

  it("renders nothing when there is nothing to say", () => {
    const { container } = render(bar({ chips: [], hasAppliedPrice: false }));
    expect(container.firstChild).toBeNull();
  });
});

// ---- UX-02B: providers ----------------------------------------------------------------------
describe("provider display names", () => {
  const names = providerNamesFrom([
    { slug: "unitree-store", name: "Unitree Online Store", type: "OEM" },
    { slug: "unitree-eu", name: "Unitree EU Store", type: "OEM" },
  ]);

  it("uses the API's name when the manufacturer lists the provider", () => {
    expect(providerLabel("unitree-store", names)).toEqual({ text: "Unitree Online Store", named: true });
  });

  it("never title-cases a slug into a company name: an unnamed seller is an identifier", () => {
    const l = providerLabel("alza-cz", names);
    expect(l).toEqual({ text: "Seller ref: alza-cz", named: false });
    expect(l.text).not.toMatch(/Alza/);
    expect(providerLabel("x", undefined).text).toBe("Seller ref: x");
  });

  it("handles several providers on one robot independently", () => {
    expect(["unitree-store", "unitree-eu", "reichelt"].map((s) => providerLabel(s, names).text)).toEqual([
      "Unitree Online Store",
      "Unitree EU Store",
      "Seller ref: reichelt",
    ]);
  });

  it("payload provider_name wins over the maker's map, which wins over the identifier", () => {
    expect(providerLabel("alza-cz", names, "Alza.cz")).toEqual({ text: "Alza.cz", named: true });
    expect(providerLabel("unitree-store", names, "Unitree Store (API)").text).toBe("Unitree Store (API)");
    expect(providerLabel("unitree-store", names, null).text).toBe("Unitree Online Store");
    expect(providerLabel("unitree-store", names, "  ").text).toBe("Unitree Online Store");
    expect(providerLabel("alza-cz", names, undefined).text).toBe("Seller ref: alza-cz");
    expect(providerLabel("alza-cz", undefined, null).text).toBe("Seller ref: alza-cz");
  });

  it("a card shows the API's provider_name with the slug kept in data-provider", () => {
    const { container } = render(
      <PriceStateCard
        price={{ type: "PUBLIC", amount: 1, currency: "CZK", provider: "alza-cz", provider_name: "Alza.cz", region: "CZ" }}
      />,
    );
    const el = container.querySelector("[data-provider]");
    expect(el?.getAttribute("data-provider")).toBe("alza-cz");
    expect(el?.textContent).toBe("Alza.cz · CZ");
  });

  it("an older API payload without provider_name still renders (identifier fallback)", () => {
    const { container } = render(
      <PriceStateCard price={{ type: "PUBLIC", amount: 1, currency: "CZK", provider: "alza-cz", region: "CZ" }} />,
    );
    expect(container.querySelector("[data-provider]")?.textContent).toBe("Seller ref: alza-cz · CZ");
    cleanup();
    const nulled = render(
      <PriceStateCard price={{ type: "PUBLIC", amount: 1, currency: "CZK", provider: "alza-cz", provider_name: null }} />,
    );
    expect(nulled.container.querySelector("[data-provider]")?.textContent).toBe("Seller ref: alza-cz");
  });

  // The API field is optional: an API that predates it (or a deploy where the web ships
  // first) sends offers with NO provider_name key at all.
  it("price payloads with provider_name absent: neutral identifier, never an invented name", () => {
    const headline: PriceDisplay = { type: "PUBLIC", amount: 917990, currency: "CZK", provider: "alza-cz", region: "CZ" };
    expect("provider_name" in headline).toBe(false);
    const { container } = render(<PriceStateCard price={headline} />);
    const el = container.querySelector("[data-provider]");
    expect(el?.textContent).toBe("Seller ref: alza-cz · CZ");
    expect(container.textContent).toContain("CZK");
    expect(container.textContent).not.toMatch(/Alza|undefined|null/);

    // the same resolver call the robot-detail pricing row makes, for two sellers on one robot
    const offers = [
      { transaction_type: "PURCHASE", price_type: "PUBLIC", provider: "alza-cz", region: "CZ" },
      { transaction_type: "PURCHASE", price_type: "PUBLIC", provider: "unitree-store", region: "GLOBAL" },
    ] as unknown as PricingOffer[];
    expect(offers.map((o) => providerLabel(o.provider!, names, o.provider_name).text)).toEqual([
      "Seller ref: alza-cz",
      "Unitree Online Store", // still named from the maker's own list
    ]);
    expect(offers.map((o) => providerLabel(o.provider!, undefined, o.provider_name).text)).toEqual([
      "Seller ref: alza-cz",
      "Seller ref: unitree-store",
    ]);
  });

  it("a price with no provider at all shows no seller line", () => {
    const { container } = render(<PriceStateCard price={{ type: "PUBLIC", amount: 1, currency: "EUR" }} />);
    expect(container.querySelector("[data-provider]")).toBeNull();
    expect(container.textContent).not.toMatch(/Seller ref|undefined|null/);
  });

  it("availability payloads with provider_name absent render unchanged", () => {
    const offers = [
      { transaction_type: "PURCHASE", availability_status: "AVAILABLE", region: "CZ", provider: "alza-cz" },
      { transaction_type: "RENTAL", availability_status: "ON_REQUEST", region: null, provider: null },
    ] as unknown as AvailabilityOffer[];
    expect(offers.every((o) => !("provider_name" in o))).toBe(true);
    const { container } = render(<AvailabilityMatrix offers={offers} />);
    const text = container.textContent ?? "";
    expect(text).toContain("Available");
    expect(text).toContain("Availability on request");
    expect(text).not.toMatch(/Alza|undefined|null/);
  });

  it("a card keeps the offer's own provider, region, basis and order note together; slug in data-provider", () => {
    const { container } = render(
      <PriceStateCard
        price={{
          type: "PUBLIC",
          amount: 29900,
          currency: "USD",
          provider: "reichelt",
          region: "DE",
          price_basis: "excludes tax, customs duties and shipping",
          order_status_note: "Not available to order at last check.",
        }}
      />,
    );
    const seller = container.querySelector("[data-provider]");
    expect(seller?.getAttribute("data-provider")).toBe("reichelt");
    expect(seller?.textContent).toBe("Seller ref: reichelt · DE");
    expect(container.textContent).toContain("Not available to order at last check.");
    expect(container.querySelector("details p")?.textContent).toBe("excludes tax, customs duties and shipping");
  });

  it("a named provider shows its name on the card when a map is supplied", () => {
    const { container } = render(
      <PriceStateCard price={{ type: "PUBLIC", amount: 1, currency: "USD", provider: "unitree-store", region: "GLOBAL" }} names={names} />,
    );
    expect(container.querySelector("[data-provider]")?.textContent).toBe("Unitree Online Store · GLOBAL");
  });
});

// ---- UX-02C: carrying the selection ----------------------------------------------------------
describe("comparison continuity resolver", () => {
  it("parses, validates, de-duplicates and caps the slug list at 4", () => {
    expect(parseSlugs("a,b,a, c ,,Bad Slug,d,e,f")).toEqual(["a", "b", "c", "d"]);
    expect(parseSlugs(null)).toEqual([]);
    expect(parseSlugs("../etc,<x>")).toEqual([]);
  });
  it("reads the selection from each carrying surface and from nothing else", () => {
    expect(selectionFromLocation("/robots", "?compare=a,b")).toEqual(["a", "b"]);
    expect(selectionFromLocation("/robots/unitree-g1", "?compare=a,b")).toEqual(["a", "b"]);
    expect(selectionFromLocation("/compare", "?ids=a,b")).toEqual(["a", "b"]);
    expect(selectionFromLocation("/compare", "?compare=a,b")).toEqual([]);
    expect(selectionFromLocation("/manufacturers", "?compare=a,b")).toEqual([]);
  });
  it("catalogue -> detail, detail -> catalogue / compare, compare -> detail", () => {
    expect(resolveNavTarget("/robots/unitree-g1", "/robots", "?compare=a,b&q=x")).toBe("/robots/unitree-g1?compare=a,b");
    expect(resolveNavTarget("/robots", "/robots/unitree-g1", "?compare=a,b")).toBe("/robots?compare=a,b");
    expect(resolveNavTarget("/compare", "/robots/unitree-g1", "?compare=a,b")).toBe("/compare?ids=a,b");
    expect(resolveNavTarget("/robots/unitree-g1", "/compare", "?ids=a,b")).toBe("/robots/unitree-g1?compare=a,b");
    expect(resolveNavTarget("/robots", "/compare", "?ids=a,b")).toBe("/robots?compare=a,b");
  });
  it("no selection, or a non-carrying target, leaves the plain href alone", () => {
    expect(resolveNavTarget("/robots/unitree-g1", "/robots", "")).toBeNull();
    expect(resolveNavTarget("/about", "/robots", "?compare=a,b")).toBeNull();
    expect(resolveNavTarget("/robots/unitree-g1/extra", "/robots", "?compare=a,b")).toBeNull();
  });
  it("toggles a slug and never exceeds 4", () => {
    expect(toggleSlug(["a", "b"], "c")).toEqual(["a", "b", "c"]);
    expect(toggleSlug(["a", "b"], "a")).toEqual(["b"]);
    expect(toggleSlug(["a", "b", "c", "d"], "e")).toEqual(["a", "b", "c", "d"]);
  });
});

describe("DetailComparisonLink (robot detail)", () => {
  const props = { slug: "unitree-g1", name: "G1", href: "/compare?ids=unitree-g1" };

  it("server HTML is one plain anchor to this robot's own compare URL, no tray", () => {
    const html = renderToStaticMarkup(<DetailComparisonLink {...props} />);
    expect(html).toContain('href="/compare?ids=unitree-g1"');
    expect(html).not.toContain("cmp-tray");
    expect(html).not.toContain("compare=");
  });

  it("with no carried selection the click navigates as before (not intercepted)", () => {
    render(<DetailComparisonLink {...props} />);
    const a = screen.getByRole("link", { name: /Compare \+/ });
    expect(fireEvent.click(a)).toBe(true); // default not prevented
    expect(screen.queryByRole("region", { name: "Compare selection" })).toBeNull();
  });

  it("with a carried selection it shows a tray and toggles THIS robot in place via the URL only", () => {
    window.history.replaceState(null, "", "/robots/unitree-g1?compare=agility-digit");
    render(<DetailComparisonLink {...props} />);
    const tray = screen.getByRole("region", { name: "Compare selection" });
    expect(tray.textContent).toContain("Compare selection: 1 / 4");
    expect(tray.textContent).toContain("Agility Digit"); // de-slugged, never the raw slug
    expect(tray.textContent).toContain("Select at least 2 to compare");
    // add this robot
    fireEvent.click(screen.getByRole("link", { name: /Compare \+/ }));
    expect(window.location.search).toBe("?compare=agility-digit%2Cunitree-g1");
    expect(selectionFromLocation(window.location.pathname, window.location.search)).toEqual(["agility-digit", "unitree-g1"]);
    expect(screen.getByRole("region", { name: "Compare selection" }).textContent).toContain("G1");
    fireEvent.click(screen.getByRole("button", { name: /Open comparison/ }));
    expect(push).toHaveBeenCalledWith("/compare?ids=agility-digit,unitree-g1");
    // remove it again
    fireEvent.click(screen.getByRole("link", { name: /In compare/ }));
    expect(selectionFromLocation(window.location.pathname, window.location.search)).toEqual(["agility-digit"]);
  });

  it("reacts to Back/Forward (popstate)", () => {
    window.history.replaceState(null, "", "/robots/unitree-g1?compare=a,b");
    render(<DetailComparisonLink {...props} />);
    expect(screen.getByRole("region", { name: "Compare selection" }).textContent).toContain("2 / 4");
    window.history.replaceState(null, "", "/robots/unitree-g1");
    fireEvent(window, new PopStateEvent("popstate"));
    expect(screen.queryByRole("region", { name: "Compare selection" })).toBeNull();
  });

  it("carries the selection on click for the server-rendered breadcrumb link", () => {
    window.history.replaceState(null, "", "/robots/unitree-g1?compare=a,b");
    render(
      <>
        <p className="idcrumb">
          {/* eslint-disable-next-line @next/next/no-html-link-for-pages -- exercises click delegation on a plain server-rendered anchor */}
          <a href="/robots">Robot Catalogue</a>
        </p>
        <DetailComparisonLink {...props} />
      </>,
    );
    fireEvent.click(screen.getByRole("link", { name: "Robot Catalogue" }));
    expect(push).toHaveBeenCalledWith("/robots?compare=a,b");
  });
});

// ---- UX-02E: visible enums -------------------------------------------------------------------
describe("visible enums", () => {
  const robot = {
    name: "Test",
    manufacturer: { name: "Maker" },
    commercial_status: "RAAS_DEPLOYMENT",
    specs: { mobility: "BIPEDAL", autonomy: "TASK_AUTONOMOUS", height_cm: 170 },
  } as unknown as RobotDetail;

  it("the Record summary block shows labels, keeps the raw enum in data-enum on the same element", () => {
    const { container } = render(<CitationFacts robot={robot} />);
    const dd = (raw: string) => container.querySelector(`dd[data-enum="${raw}"]`);
    expect(dd("RAAS_DEPLOYMENT")?.textContent).toBe("Robot-as-a-service");
    expect(dd("TASK_AUTONOMOUS")?.textContent).toBe("Task-autonomous");
    expect(dd("BIPEDAL")?.textContent).toBe("Bipedal");
    expect(container.textContent).not.toMatch(/[A-Z]+_[A-Z_]+/);
    // numbers stay plain text with no data-enum
    expect(Array.from(container.querySelectorAll("dd")).find((d) => d.textContent === "170 cm")?.hasAttribute("data-enum")).toBe(false);
  });

  it("the machine projection (citationFacts) is untouched: raw, verbatim enums", () => {
    const facts = new Map(citationFacts(robot).map((f) => [f.label, f.value]));
    expect(facts.get("Commercial status")).toBe("RAAS_DEPLOYMENT");
    expect(facts.get("Mobility")).toBe("BIPEDAL");
    expect(facts.get("Autonomy")).toBe("TASK_AUTONOMOUS");
  });

  it("extended-spec category headings map AI_AUTONOMY and fall back readably", () => {
    expect(enumLabel("capability_category", "AI_AUTONOMY")).toBe("AI and autonomy");
    expect(enumLabel("capability_category", "SOME_NEW_GROUP")).toBe("Some new group");
  });
});
