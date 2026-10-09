// UX-02A - deterministic catalogue query interpreter.
//
// A pure function: the same text and vocabulary always give the same result. No
// I/O, no randomness, no LLM, no fuzzy or semantic matching - only exact words,
// exact phrases and a small static synonym table whose targets are checked
// against the real vocabulary. It turns a buyer's sentence ("warehouse robot under
// EUR 20k") into the SAME filters the catalogue already has; it never invents a
// fact and never answers a question the catalogue cannot.
//
// What each filter means is decided by the API, not here (see docs in
// apps/api/app/services/robot_filters.py / pricing.py):
//   manufacturer   exact manufacturer slug
//   use_case       exact use-case slug (robots with a recorded fit)
//   transaction_type  robots with a CURRENT, commercially-accessible AVAILABILITY
//                  offer in that mode - an obtainability filter, not a price
//   price_max + price_currency  robots with a current NEW PURCHASE pricing offer
//                  denominated exactly in that currency whose comparable amount
//                  (PUBLIC/FROM/ESTIMATED/MANUFACTURER_ESTIMATE price, or a RANGE's
//                  upper bound) is <= the ceiling. No conversion; QUOTE_ONLY and
//                  unknown prices never match; a rental rate is never a purchase price.
//   q (residual)   full-text over robot name, model code, summary, description
//
// A number without a currency is NEVER applied and never defaulted.

export interface InterpreterVocab {
  manufacturers: { slug: string; name: string }[];
  useCases: { slug: string; name: string }[];
}

/** Currencies the catalogue records purchase prices in (matched exactly, no FX). */
export const SUPPORTED_CURRENCIES = ["USD", "EUR", "GBP", "CZK"] as const;
export type SupportedCurrency = (typeof SUPPORTED_CURRENCIES)[number];

export type ChipKind = "manufacturer" | "use_case" | "transaction_type" | "price";
export type ChipStatus = "applied" | "needs_currency" | "not_applied";

export interface Chip {
  kind: ChipKind;
  /** Visible text, e.g. "Use case: Warehouse & Logistics". */
  label: string;
  status: ChipStatus;
  /** Why it is not applied, or a short interpretation note (e.g. "'industrial' read as ..."). */
  note?: string;
  /** Character span in the (trimmed) query text this chip was read from. */
  start: number;
  end: number;
}

export interface InterpretedFilters {
  manufacturer?: string;
  use_case?: string;
  transaction_type?: string[];
  price_max?: number;
  price_currency?: string;
}

export interface Interpretation {
  /** The trimmed input the spans refer to. */
  text: string;
  filters: InterpretedFilters;
  /** Remaining words: sent to the API as `q` (name / description search). */
  residual: string;
  needsCurrency: boolean;
  /** Recognised but not supportable (minimum price, unknown currency, ambiguous number...). */
  unsupported: string[];
  conflicts: string[];
  chips: Chip[];
}

const MAX_QUERY_LENGTH = 200;

// Words that carry no filter: dropped silently.
const FILLER = new Set(["robot", "robots", "humanoid", "humanoids", "a", "an", "for", "the", "with"]);

// Buyer words -> EXISTING canonical use-case slugs. A target absent from the vocabulary
// is simply not mapped. Doubtful mappings carry a note shown on the chip.
const USE_CASE_SYNONYMS: Record<string, { slug: string; note?: string }> = {
  warehouse: { slug: "warehouse-logistics" },
  warehousing: { slug: "warehouse-logistics" },
  logistics: { slug: "warehouse-logistics" },
  fulfilment: { slug: "warehouse-logistics" },
  fulfillment: { slug: "warehouse-logistics" },
  retail: { slug: "retail-service" },
  hospitality: { slug: "retail-service" },
  reception: { slug: "retail-service" },
  service: { slug: "retail-service" },
  inspection: { slug: "security-inspection" },
  security: { slug: "security-inspection" },
  patrol: { slug: "security-inspection" },
  research: { slug: "research-education" },
  education: { slug: "research-education" },
  university: { slug: "research-education" },
  lab: { slug: "research-education" },
  manufacturing: { slug: "manufacturing" },
  factory: { slug: "manufacturing" },
  assembly: { slug: "manufacturing" },
  industrial: { slug: "manufacturing", note: "“industrial” read as Manufacturing" },
  healthcare: { slug: "healthcare-rehabilitation" },
  hospital: { slug: "healthcare-rehabilitation" },
  rehab: { slug: "healthcare-rehabilitation" },
  rehabilitation: { slug: "healthcare-rehabilitation" },
  home: { slug: "home" },
  household: { slug: "home" },
  events: { slug: "events-entertainment" },
  entertainment: { slug: "events-entertainment" },
  exhibition: { slug: "events-entertainment" },
};

// Only transaction_type values the catalogue filter supports.
const TRANSACTION_WORDS: Record<string, string> = {
  buy: "PURCHASE",
  purchase: "PURCHASE",
  rent: "RENTAL",
  rental: "RENTAL",
  hire: "RENTAL",
  lease: "LEASE",
  subscription: "SUBSCRIPTION",
  raas: "RAAS",
};
const TRANSACTION_LABEL: Record<string, string> = {
  PURCHASE: "Purchase",
  RENTAL: "Rental",
  LEASE: "Lease",
  SUBSCRIPTION: "Subscription",
  RAAS: "Robot-as-a-service",
};

const CURRENCY_WORDS: Record<string, string> = {
  "€": "EUR", eur: "EUR", euro: "EUR", euros: "EUR",
  $: "USD", usd: "USD", dollar: "USD", dollars: "USD",
  "£": "GBP", gbp: "GBP", pound: "GBP", pounds: "GBP",
  "kč": "CZK", czk: "CZK", crown: "CZK", crowns: "CZK",
  cny: "CNY", rmb: "CNY", yuan: "CNY",
  jpy: "JPY", yen: "JPY", chf: "CHF", cad: "CAD", aud: "AUD",
};

const CUR = "[€$£]|kč|eur(?:os?)?|usd|dollars?|gbp|pounds?|czk|crowns?|cny|rmb|yuan|jpy|yen|chf|cad|aud";
const UPPER = "under|below|up\\s*to|upto|max(?:imum)?|less\\s+than|at\\s+most|no\\s+more\\s+than|within|<=?";
const LOWER = "over|above|more\\s+than|at\\s+least|min(?:imum)?|>=?";
const PRICE_RE = new RegExp(
  `(?<![a-z])(${UPPER}|${LOWER})\\s*(?:(${CUR})\\s*)?(\\d+(?:[.,]\\d+)*)\\s*(k(?![a-z0-9]))?\\s*(?:(${CUR})(?![a-z]))?`,
  "giu",
);
const UPPER_RE = new RegExp(`^(?:${UPPER})$`, "i");

// Alias generic suffix words stripped from manufacturer names ("Unitree Robotics" -> "unitree").
const GENERIC_SUFFIX = new Set([
  "robotics", "robot", "technologies", "technology", "intelligence", "dynamics", "ai", "inc", "ltd", "co",
]);

function norm(s: string): string {
  return s
    .toLowerCase()
    .replace(/&/g, " ")
    .replace(/[^\p{L}\p{N}]+/gu, " ")
    .trim();
}

interface Alias {
  words: string[];
  slug: string;
}

/** Exact manufacturer aliases: slug, full name, and the name without generic suffix words. */
function buildAliases(vocab: InterpreterVocab): Alias[] {
  const bySlugs = new Map<string, Set<string>>(); // alias string -> manufacturer slugs
  for (const m of vocab.manufacturers) {
    const full = norm(m.name);
    const words = full.split(" ").filter(Boolean);
    const core = words.filter((w, i) => !(i > 0 && GENERIC_SUFFIX.has(w)));
    for (const a of [norm(m.slug), full, core.join(" ")]) {
      if (!a) continue;
      if (a.length < 3 && !/\d/.test(a)) continue;
      if (!bySlugs.has(a)) bySlugs.set(a, new Set());
      bySlugs.get(a)!.add(m.slug);
    }
  }
  const out: Alias[] = [];
  for (const [a, slugs] of bySlugs) {
    if (slugs.size !== 1) continue; // an alias shared by two makers identifies neither
    out.push({ words: a.split(" "), slug: [...slugs][0] });
  }
  // Longest alias first so "boston dynamics" wins over any shorter overlap.
  out.sort((x, y) => y.words.length - x.words.length || y.words.join(" ").length - x.words.join(" ").length);
  return out;
}

function formatAmount(n: number, cur: string): string {
  const num = n.toLocaleString("en-US", { maximumFractionDigits: 2 });
  const symbol = { USD: "$", EUR: "€", GBP: "£" }[cur as "USD" | "EUR" | "GBP"];
  return symbol ? `${symbol}${num}` : `${cur} ${num}`;
}

interface PriceHit {
  bound: "upper" | "lower";
  amount: number | null;
  currency: string | null; // resolved code or null
  start: number;
  end: number;
  raw: string;
  ambiguous: boolean;
  dollarSign: boolean;
}

function parseAmount(numStr: string, k: boolean): { value: number | null; ambiguous: boolean } {
  let v: number;
  if (/^\d{1,3}(,\d{3})+$/.test(numStr)) v = Number(numStr.replace(/,/g, ""));
  else if (/^\d{1,3}(\.\d{3})+$/.test(numStr)) return { value: null, ambiguous: true }; // 20.000: 20 or 20,000?
  else if (/^\d+(\.\d+)?$/.test(numStr)) v = Number(numStr);
  else return { value: null, ambiguous: true };
  if (k) v *= 1000;
  return Number.isFinite(v) && v > 0 ? { value: v, ambiguous: false } : { value: null, ambiguous: true };
}

export function interpretQuery(input: string, vocab: InterpreterVocab): Interpretation {
  const text = (input ?? "").replace(/\s+/g, " ").trim().slice(0, MAX_QUERY_LENGTH);
  const consumed = new Array<boolean>(text.length).fill(false);
  const chips: Chip[] = [];
  const unsupported: string[] = [];
  const conflicts: string[] = [];
  const free = (s: number, e: number) => {
    for (let i = s; i < e; i++) if (consumed[i]) return false;
    return true;
  };
  const take = (s: number, e: number) => {
    for (let i = s; i < e; i++) consumed[i] = true;
  };

  // ---- 1. price phrases -------------------------------------------------------
  const hits: PriceHit[] = [];
  for (const m of text.matchAll(PRICE_RE)) {
    const start = m.index ?? 0;
    const end = start + m[0].trimEnd().length;
    if (!free(start, end)) continue;
    const kw = m[1].toLowerCase().replace(/\s+/g, " ");
    const pre = m[2]?.toLowerCase();
    const post = m[5]?.toLowerCase();
    const parsed = parseAmount(m[3], !!m[4]);
    const preCode = pre ? CURRENCY_WORDS[pre] : undefined;
    const postCode = post ? CURRENCY_WORDS[post] : undefined;
    let currency: string | null = preCode ?? postCode ?? null;
    if (preCode && postCode && preCode !== postCode) {
      conflicts.push(`Two different currencies in one price (${preCode} and ${postCode}).`);
      currency = null;
    }
    hits.push({
      bound: UPPER_RE.test(kw) ? "upper" : "lower",
      amount: parsed.value,
      currency,
      start,
      end,
      raw: text.slice(start, end),
      ambiguous: parsed.ambiguous,
      dollarSign: pre === "$" || post === "$",
    });
    take(start, end);
  }

  const uppers = hits.filter((h) => h.bound === "upper");
  const lowers = hits.filter((h) => h.bound === "lower");
  let price: { max: number; currency: string } | null = null;
  let needsCurrency = false;

  for (const h of lowers) {
    unsupported.push(`Minimum price (“${h.raw}”) – the catalogue can only filter by a maximum price.`);
    chips.push({
      kind: "price",
      label: `Minimum price: ${h.raw}`,
      status: "not_applied",
      note: "Not applied: minimum price is not a catalogue filter.",
      start: h.start,
      end: h.end,
    });
  }

  const usable = uppers.filter((h) => h.amount != null);
  for (const h of uppers) {
    if (h.amount == null) {
      unsupported.push(`Price “${h.raw}” – the number is ambiguous (for example 20.000), so no price was applied. Write it as 20000.`);
      chips.push({
        kind: "price",
        label: `Maximum purchase price: ${h.raw}`,
        status: "not_applied",
        note: "Not applied: the number is ambiguous.",
        start: h.start,
        end: h.end,
      });
    }
  }
  const distinct = new Set(usable.map((h) => `${h.amount}|${h.currency ?? ""}`));
  if (distinct.size > 1) {
    conflicts.push("More than one maximum price in the query; none was applied.");
    for (const h of usable) {
      chips.push({
        kind: "price",
        label: `Maximum purchase price: ${h.raw}`,
        status: "not_applied",
        note: "Not applied: conflicts with another price in the query.",
        start: h.start,
        end: h.end,
      });
    }
  } else if (usable.length > 0) {
    const h = usable[0];
    const dup = usable.slice(1);
    const amount = h.amount as number;
    if (h.currency == null) {
      needsCurrency = true;
      chips.push({
        kind: "price",
        label: `Maximum purchase price ${amount.toLocaleString("en-US")} — choose a currency`,
        status: "needs_currency",
        note: "Not applied: no currency was given and none is assumed.",
        start: h.start,
        end: h.end,
      });
    } else if (!(SUPPORTED_CURRENCIES as readonly string[]).includes(h.currency)) {
      unsupported.push(`Currency ${h.currency} – the catalogue records purchase prices in ${SUPPORTED_CURRENCIES.join(", ")} only.`);
      chips.push({
        kind: "price",
        label: `Maximum purchase price: ${h.currency} ${amount.toLocaleString("en-US")}`,
        status: "not_applied",
        note: `Not applied: no recorded purchase prices in ${h.currency}.`,
        start: h.start,
        end: h.end,
      });
    } else {
      price = { max: amount, currency: h.currency };
      chips.push({
        kind: "price",
        label: `Maximum purchase price: ${formatAmount(amount, h.currency)}`,
        status: "applied",
        note: h.dollarSign ? "“$” read as US dollars." : undefined,
        start: h.start,
        end: h.end,
      });
    }
    for (const d of dup) take(d.start, d.end);
  }
  if (price && lowers.length > 0) {
    const lo = lowers.find((l) => l.amount != null && l.currency === price!.currency);
    if (lo && (lo.amount as number) >= price.max) {
      conflicts.push("The minimum price is not below the maximum price; nothing can match both.");
    }
  }

  // ---- 2. fixed phrases -------------------------------------------------------
  const transactions: { code: string; start: number; end: number }[] = [];
  const useCaseHits: { slug: string; start: number; end: number; note?: string }[] = [];
  const useCaseSlugs = new Set(vocab.useCases.map((u) => u.slug));

  for (const m of text.matchAll(/(?<![a-z])robot[-\s]as[-\s]a[-\s]service(?![a-z])/gi)) {
    const s = m.index ?? 0;
    const e = s + m[0].length;
    if (!free(s, e)) continue;
    transactions.push({ code: "RAAS", start: s, end: e });
    take(s, e);
  }
  for (const m of text.matchAll(/(?<![a-z])industrial\s+inspection(?![a-z])/gi)) {
    const s = m.index ?? 0;
    const e = s + m[0].length;
    if (!free(s, e) || !useCaseSlugs.has("security-inspection")) continue;
    useCaseHits.push({ slug: "security-inspection", start: s, end: e, note: "“industrial inspection” read as Security & Inspection" });
    take(s, e);
  }

  // ---- 3. manufacturers (exact alias, word-boundary) --------------------------
  const mfrHits: { slug: string; start: number; end: number }[] = [];
  for (const a of buildAliases(vocab)) {
    const re = new RegExp(`(?<![\\p{L}\\p{N}])${a.words.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("[\\s-]+")}(?![\\p{L}\\p{N}])`, "giu");
    for (const m of text.matchAll(re)) {
      const s = m.index ?? 0;
      const e = s + m[0].length;
      if (!free(s, e)) continue;
      mfrHits.push({ slug: a.slug, start: s, end: e });
      take(s, e);
    }
  }

  // ---- 4. single words --------------------------------------------------------
  const residualTokens: string[] = [];
  for (const m of text.matchAll(/[\p{L}\p{N}][\p{L}\p{N}'-]*/gu)) {
    const s = m.index ?? 0;
    const e = s + m[0].length;
    if (!free(s, e)) continue;
    const w = m[0].toLowerCase();
    if (FILLER.has(w)) {
      take(s, e);
    } else if (TRANSACTION_WORDS[w]) {
      transactions.push({ code: TRANSACTION_WORDS[w], start: s, end: e });
      take(s, e);
    } else if (USE_CASE_SYNONYMS[w] && useCaseSlugs.has(USE_CASE_SYNONYMS[w].slug)) {
      useCaseHits.push({ slug: USE_CASE_SYNONYMS[w].slug, start: s, end: e, note: USE_CASE_SYNONYMS[w].note });
      take(s, e);
    } else {
      residualTokens.push(m[0]);
    }
  }

  // ---- 5. assemble ------------------------------------------------------------
  const filters: InterpretedFilters = {};
  const mfrName = new Map(vocab.manufacturers.map((m) => [m.slug, m.name]));
  const ucName = new Map(vocab.useCases.map((u) => [u.slug, u.name]));

  const mfrSlugs = [...new Set(mfrHits.map((h) => h.slug))];
  if (mfrSlugs.length > 1) {
    conflicts.push(`Two manufacturers in one query (${mfrSlugs.map((s) => mfrName.get(s)).join(" and ")}); none was applied.`);
  } else if (mfrSlugs.length === 1) {
    filters.manufacturer = mfrSlugs[0];
  }
  for (const h of mfrHits) {
    chips.push({
      kind: "manufacturer",
      label: `Manufacturer: ${mfrName.get(h.slug)}`,
      status: mfrSlugs.length > 1 ? "not_applied" : "applied",
      note: mfrSlugs.length > 1 ? "Not applied: conflicts with another manufacturer." : undefined,
      start: h.start,
      end: h.end,
    });
  }

  const ucSlugs = [...new Set(useCaseHits.map((h) => h.slug))];
  if (ucSlugs.length > 1) {
    conflicts.push(`Two use cases in one query (${ucSlugs.map((s) => ucName.get(s)).join(" and ")}); the catalogue filters by one, so none was applied.`);
  } else if (ucSlugs.length === 1) {
    filters.use_case = ucSlugs[0];
  }
  for (const h of useCaseHits) {
    chips.push({
      kind: "use_case",
      label: `Use case: ${ucName.get(h.slug) ?? h.slug}`,
      status: ucSlugs.length > 1 ? "not_applied" : "applied",
      note: ucSlugs.length > 1 ? "Not applied: conflicts with another use case." : h.note,
      start: h.start,
      end: h.end,
    });
  }

  const txCodes = [...new Set(transactions.map((t) => t.code))];
  if (txCodes.length) filters.transaction_type = txCodes;
  for (const t of transactions) {
    chips.push({
      kind: "transaction_type",
      label: `Obtainable by: ${TRANSACTION_LABEL[t.code]}`,
      status: "applied",
      note: "Matches robots with a recorded, accessible offer in this mode. It is not a price.",
      start: t.start,
      end: t.end,
    });
  }

  if (price) {
    filters.price_max = price.max;
    filters.price_currency = price.currency;
  }

  chips.sort((a, b) => a.start - b.start);
  return {
    text,
    filters,
    residual: residualTokens.join(" "),
    needsCurrency,
    unsupported,
    conflicts,
    chips,
  };
}

/** The query text with one chip's words removed (the chip's "remove" action). */
export function removeChip(text: string, chip: Pick<Chip, "start" | "end">): string {
  return `${text.slice(0, chip.start)} ${text.slice(chip.end)}`.replace(/\s+/g, " ").trim();
}

/** The query text with an explicit currency added after a currency-less price chip. */
export function addCurrencyToChip(text: string, chip: Pick<Chip, "start" | "end">, currency: SupportedCurrency): string {
  return `${text.slice(0, chip.end)} ${currency}${text.slice(chip.end)}`.replace(/\s+/g, " ").trim();
}
