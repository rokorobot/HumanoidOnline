# Unitree adapter `unitree-robotics-official@0.1.0`: evidence contract and limitations

Module: `apps/api/app/services/discovery/sources/unitree_robotics.py`. Structural basis:
`UNITREE_STRUCTURAL_REVIEW_2026-10-18.md`. Access basis: docs/28 (A4) `OWNER_AUTHORIZED`, which
is not publisher consent; `tos_status` stays UNKNOWN. This document states exactly what the adapter
records, in which discovery-layer row, and what it never does.

## Scope

- Host `www.unitree.com` only. `unistore.unitree.com` and every other subdomain are out of scope.
- Three fixed seeds, `https://www.unitree.com/H2`, `/R1`, `/g1`. Each answers a same-host 302 to the
  trailing-slash URL that serves the page. No link-following (`target_cap = 1`). The `/cn/`-only
  sitemap is never read.
- Path prefixes the source must have reviewed and owner-authorized: `/H2`, `/R1`, `/g1`.
  `/H2plus`, `/H2-D`, `/G1-D`, `/R1-7a` … are other models and are not covered.

## What one run records (discovery layer only)

Per page, one `discovery_candidate` (the page's MODEL), and its `candidate_claim`,
`candidate_commercial_signal` and `discovery_evidence_excerpt` rows. Every value carries a verbatim
excerpt (≤ 1000 characters) and a locator. The run, the fetched pages (URL, status, hash, retrieval
time) and the retained raw body give the source URL and observation timestamp.

| Fact | Row | Key / type | Value |
|---|---|---|---|
| Model identity | candidate | `candidate_name` = `H2` / `R1` / `G1`; manufacturer `Unitree Robotics` | slug, edition list and `<title>` token must all agree |
| Editions on the page | claim | `unitree.editions` | `H2; H2 EDU` (verbatim, page order) |
| Specifications | claim | `unitree.spec[<edition>]/<category>/<label>` | verbatim cell text, `unit = NULL` (e.g. `About 70kg`, `26-40`) |
| Price terms | claim | `unitree.price_terms` | `Price（Tax and Shipping cost excluded）` (verbatim) |
| Price per edition | claim | `unitree.price[<edition>]` | verbatim cell: `$29,900`, `Contact Sales`, `US $13.5K` |
| "from" price | claim + signal | `unitree.price_from`; signal `PRICE / FROM` | `Price from $4,900` (hero line) |
| Model's own price | signal | `PRICE / PUBLIC` (amount) or `PRICE / QUOTE_ONLY` (Contact Sales) | page-model row only |

**Money is fail-closed.**
- `price_currency` is set only when the page states the currency: `US $` gives `USD`, while a bare
  `$` leaves it NULL.
- `price_amount` is set only for an exact `US $12,345` statement. A `K` suffix is never expanded,
  and a bare `$` gives no amount.
- On the 2026-10-18 pages this means **no signal carries an amount**. G1's signal carries
  `USD` without an amount. Everything else is in the excerpts.
- `region_code` is always NULL. No VAT, no EU price and no availability is inferred.

EDU rows (`H2 EDU`, `R1 EDU`, `G1 EDU`) and `R1 AIR` are **never** signals on the model's candidate.
Their prices and specifications exist only as edition-keyed claims.

## Never

- **No canonical write.** The `unitree.*` claim keys are outside promotion's approved fields, so no
  claim can become a catalogue fact without the separately governed trace, review, claim and import
  chain. A test pins this.
- **No edition → catalogue robot mapping.** The catalogue has `unitree-h2`, `unitree-h2-edu`,
  `unitree-r1`, `unitree-r1-edu-u1…u6`, `unitree-g1-basic`, `unitree-g1-edu-plus-u2`. Stage E
  resolves the page model by the existing exact rules only. Expected: `H2` and `R1` may match the
  same-named robots. `G1` has no exact catalogue name (`G1 Basic`) and goes to human review. Editions
  are always a human decision.
- No proposal ingestion (G2): nothing attaches to a catalogue robot automatically.
- No retry of a block (401/403/429 halt the run; the scheduler does not retry a halt). No alternate
  identity, proxy or challenge solving. A robots disallow is honoured, including behind the UTF-8
  BOM the site serves. The shared parser previously ignored a BOM-prefixed group, a fail-open
  defect fixed in this PR.

## Reliably captured vs unsupported

**Reliable:**
- model identity for H2, R1 and G1;
- the edition list;
- every specification row as verbatim text per edition;
- each edition's price statement verbatim;
- the tax-and-shipping exclusion;
- "from" and contact-sales wording;
- change detection between observations (conditional GET, unchanged pages add nothing).

**Unsupported:**
- numeric amounts for bare-`$` or `K`-suffixed prices;
- currency for bare `$`;
- VAT, shipping or regional (EU) prices;
- availability, stock, lead time and orderability;
- the store host;
- models beyond the three reviewed pages;
- edition-level identity;
- specifications as typed numbers or units;
- any value that only images or videos show.

## Owner decisions before any of this reaches the catalogue

1. **Price semantics:** is a manufacturer USD price "excluding tax and shipping" on the global site a
   `PUBLIC` price for the catalogue, and in which region?
2. Is a bare `$` USD? Should the `K` suffix be expanded?
3. **Edition identity:** which page editions map to which catalogue robots or variants.
4. **Activation (separately approved):** applying migration 0025, then `source review`, `authorize-owner`,
   `enable` and `cadence` for `unitree-robotics-official`.
