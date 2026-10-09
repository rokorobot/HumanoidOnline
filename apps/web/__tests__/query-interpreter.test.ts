// UX-02A - the deterministic query interpreter (table-driven).
import { describe, expect, it } from "vitest";

import {
  addCurrencyToChip,
  interpretQuery,
  removeChip,
  type InterpreterVocab,
} from "../lib/query-interpreter";

const vocab: InterpreterVocab = {
  manufacturers: [
    { slug: "unitree", name: "Unitree Robotics" },
    { slug: "figure-ai", name: "Figure" },
    { slug: "agility-robotics", name: "Agility Robotics" },
    { slug: "boston-dynamics", name: "Boston Dynamics" },
    { slug: "1x-technologies", name: "1X Technologies" },
    { slug: "neura-robotics", name: "Neura Robotics" },
    { slug: "pal-robotics", name: "PAL Robotics" },
  ],
  useCases: [
    { slug: "warehouse-logistics", name: "Warehouse & Logistics" },
    { slug: "retail-service", name: "Retail & Service" },
    { slug: "security-inspection", name: "Security & Inspection" },
    { slug: "research-education", name: "Research & Education" },
    { slug: "manufacturing", name: "Manufacturing" },
    { slug: "healthcare-rehabilitation", name: "Healthcare & Rehabilitation" },
    { slug: "home", name: "Home" },
    { slug: "events-entertainment", name: "Events & Entertainment" },
  ],
};

describe("interpretQuery - single concepts", () => {
  const rows: [string, Record<string, unknown>, string][] = [
    ["unitree", { manufacturer: "unitree" }, ""],
    ["Unitree Robotics", { manufacturer: "unitree" }, ""],
    ["boston dynamics", { manufacturer: "boston-dynamics" }, ""],
    ["digit", {}, "digit"],
    ["G1", {}, "G1"],
    ["unitree g1", { manufacturer: "unitree" }, "g1"],
    ["logistics", { use_case: "warehouse-logistics" }, ""],
    ["hospital", { use_case: "healthcare-rehabilitation" }, ""],
    ["factory", { use_case: "manufacturing" }, ""],
    ["buy", { transaction_type: ["PURCHASE"] }, ""],
    ["rent", { transaction_type: ["RENTAL"] }, ""],
    ["hire a robot", { transaction_type: ["RENTAL"] }, ""],
    ["lease", { transaction_type: ["LEASE"] }, ""],
    ["robot-as-a-service", { transaction_type: ["RAAS"] }, ""],
    ["RaaS", { transaction_type: ["RAAS"] }, ""],
    ["the humanoid robot with hands", {}, "hands"],
  ];
  it.each(rows)("%s", (input, filters, residual) => {
    const r = interpretQuery(input, vocab);
    expect(r.filters).toEqual(filters);
    expect(r.residual).toBe(residual);
    expect(r.conflicts).toEqual([]);
  });
});

describe("interpretQuery - prices", () => {
  const rows: [string, number, string][] = [
    ["under €20,000", 20000, "EUR"],
    ["below 20000 EUR", 20000, "EUR"],
    ["up to $30000", 30000, "USD"],
    ["under 20k usd", 20000, "USD"],
    ["max 20k eur", 20000, "EUR"],
    ["less than 1.5k GBP", 1500, "GBP"],
    ["<20000€", 20000, "EUR"],
    ["under 450000 czk", 450000, "CZK"],
    ["under £12,500", 12500, "GBP"],
  ];
  it.each(rows)("%s", (input, max, cur) => {
    const r = interpretQuery(input, vocab);
    expect(r.filters.price_max).toBe(max);
    expect(r.filters.price_currency).toBe(cur);
    expect(r.needsCurrency).toBe(false);
    expect(r.residual).toBe("");
    const chip = r.chips.find((c) => c.kind === "price");
    expect(chip?.status).toBe("applied");
    expect(chip?.label).toMatch(/^Maximum purchase price: /);
  });

  it("a number with NO currency is not applied and not defaulted", () => {
    const r = interpretQuery("under 20000", vocab);
    expect(r.needsCurrency).toBe(true);
    expect(r.filters.price_max).toBeUndefined();
    expect(r.filters.price_currency).toBeUndefined();
    const chip = r.chips[0];
    expect(chip.status).toBe("needs_currency");
    expect(chip.label).toBe("Maximum purchase price 20,000 — choose a currency");
    // choosing a currency rewrites the query text only; the result is then applied
    const text = addCurrencyToChip(r.text, chip, "EUR");
    expect(text).toBe("under 20000 EUR");
    expect(interpretQuery(text, vocab).filters).toEqual({ price_max: 20000, price_currency: "EUR" });
  });

  it("$ is read as USD and says so", () => {
    const chip = interpretQuery("under $5000", vocab).chips[0];
    expect(chip.note).toMatch(/US dollars/);
  });

  it("an unsupported currency is recognised but not applied", () => {
    const r = interpretQuery("under 20000 cny", vocab);
    expect(r.filters.price_max).toBeUndefined();
    expect(r.unsupported.join(" ")).toMatch(/CNY/);
    expect(r.chips[0].status).toBe("not_applied");
  });

  it("an ambiguous number (20.000) is never guessed", () => {
    const r = interpretQuery("under 20.000 eur", vocab);
    expect(r.filters.price_max).toBeUndefined();
    expect(r.unsupported.join(" ")).toMatch(/ambiguous/);
  });

  it("a minimum price is unsupported and never applied as a maximum", () => {
    const r = interpretQuery("over 20000 eur", vocab);
    expect(r.filters.price_max).toBeUndefined();
    expect(r.unsupported.join(" ")).toMatch(/Minimum price/);
  });

  it("a maximum and a not-lower minimum conflict", () => {
    const r = interpretQuery("under 20000 EUR over 25000 EUR", vocab);
    expect(r.conflicts.join(" ")).toMatch(/nothing can match both/);
  });

  it("two different maxima conflict and apply none", () => {
    const r = interpretQuery("under 20000 EUR under 30000 EUR", vocab);
    expect(r.filters.price_max).toBeUndefined();
    expect(r.conflicts.join(" ")).toMatch(/More than one maximum price/);
  });

  it("two currencies in one price conflict", () => {
    const r = interpretQuery("under €20000 usd", vocab);
    expect(r.conflicts.join(" ")).toMatch(/Two different currencies/);
    expect(r.filters.price_max).toBeUndefined();
  });

  it("the price words are never left in the name search", () => {
    expect(interpretQuery("digit under 20k usd", vocab).residual).toBe("digit");
  });
});

describe("interpretQuery - compounds", () => {
  it("warehouse robot under €20000", () => {
    const r = interpretQuery("warehouse robot under €20000", vocab);
    expect(r.filters).toEqual({ use_case: "warehouse-logistics", price_max: 20000, price_currency: "EUR" });
    expect(r.residual).toBe("");
    expect(r.chips.map((c) => c.label)).toEqual([
      "Use case: Warehouse & Logistics",
      "Maximum purchase price: €20,000",
    ]);
  });
  it("unitree research under $20000 purchase", () => {
    const r = interpretQuery("unitree research under $20000 purchase", vocab);
    expect(r.filters).toEqual({
      manufacturer: "unitree",
      use_case: "research-education",
      transaction_type: ["PURCHASE"],
      price_max: 20000,
      price_currency: "USD",
    });
    expect(r.residual).toBe("");
  });
  it("industrial inspection maps to Security & Inspection and says so", () => {
    const r = interpretQuery("industrial inspection", vocab);
    expect(r.filters.use_case).toBe("security-inspection");
    expect(r.chips[0].note).toMatch(/industrial inspection/);
  });
  it("bare industrial maps to Manufacturing and says so", () => {
    const r = interpretQuery("industrial", vocab);
    expect(r.filters.use_case).toBe("manufacturing");
    expect(r.chips[0].note).toMatch(/Manufacturing/);
  });
  it("as-a-service is RaaS, not the retail 'service' word", () => {
    const r = interpretQuery("robot as a service", vocab);
    expect(r.filters).toEqual({ transaction_type: ["RAAS"] });
  });
  it("a synonym whose target is not in the vocabulary is not mapped", () => {
    const r = interpretQuery("warehouse", { ...vocab, useCases: [] });
    expect(r.filters.use_case).toBeUndefined();
    expect(r.residual).toBe("warehouse");
  });
});

describe("interpretQuery - conflicts and unsupported terms", () => {
  it("two manufacturers", () => {
    const r = interpretQuery("unitree figure", vocab);
    expect(r.filters.manufacturer).toBeUndefined();
    expect(r.conflicts.join(" ")).toMatch(/Two manufacturers/);
    expect(r.chips.every((c) => c.status === "not_applied")).toBe(true);
  });
  it("two use cases", () => {
    const r = interpretQuery("warehouse retail", vocab);
    expect(r.filters.use_case).toBeUndefined();
    expect(r.conflicts.join(" ")).toMatch(/Two use cases/);
  });
  it("an unknown word stays in the name search (the server reports it unmatched)", () => {
    const r = interpretQuery("waterproof", vocab);
    expect(r.residual).toBe("waterproof");
    expect(r.chips).toEqual([]);
  });
  it("is deterministic and trims/collapses whitespace", () => {
    const a = interpretQuery("  unitree   g1  ", vocab);
    expect(a).toEqual(interpretQuery("unitree g1", vocab));
    expect(a.text).toBe("unitree g1");
  });
  it("empty input interprets to nothing", () => {
    const r = interpretQuery("", vocab);
    expect(r.filters).toEqual({});
    expect(r.chips).toEqual([]);
  });
});

describe("chip removal edits only that chip's words", () => {
  it("removes the price phrase and keeps the rest", () => {
    const r = interpretQuery("warehouse robot under €20000", vocab);
    const price = r.chips.find((c) => c.kind === "price")!;
    expect(removeChip(r.text, price)).toBe("warehouse robot");
    const uc = r.chips.find((c) => c.kind === "use_case")!;
    expect(removeChip(r.text, uc)).toBe("robot under €20000");
  });
});
