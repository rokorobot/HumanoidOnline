# HO-RESEARCH-NA-01 — North America Research Resource: evidence audit, readiness and proposed batch

**Date:** 2026-10-23 · **Status:** review package, nothing published, nothing written to production.
**Resource:** `/research/humanoid-availability/north-america` (+ `.json`). Built on the same ADR-027 read model, projection, gate, JSON-LD, sitemap and preview session as Europe.

## 1. Verdict

| | Result |
|---|---|
| Published robots (population) | 43 |
| Robots with a qualifying North America offer | **3**: Unitree G1 (RobotShop US), 1X NEO (1X store, preorder), Agility Digit (RaaS, on request) |
| Manufacturers with a qualifying offer | **3** |
| Launch gate (5 robots / 3 manufacturers, unchanged) | **FAILS** on robots only (3 < 5) |
| Publication health | LIMITED_EVIDENCE (3 qualifying robots; minimum 5) |
| Groups reconcile | yes (3 + 1 + 4 + 14 + 21 = 43) |

**Owner decision 2026-10-23 (amends ADR-027 §12):** an offer and its price stay current until newer evidence replaces them. Evidence age alone no longer removes an offer; each offer shows its last-observed date. Before this decision, the same data gave 1 robot / 1 manufacturer: NEO and Digit had aged past the 90-day window, and G1 would have aged out on 2026-11-16.

**North America stays unpublished.** The code, data hierarchy and article are complete and tested, but two more qualifying robots are needed.

How the figures were obtained: the production catalogue was read with a read-only transaction (Neon `production`, `SET TRANSACTION READ ONLY`), loaded through the real `load_regional_snapshot`, and the proposed NORTH_AMERICA hierarchy was applied **in memory only**. The local full stack built from the repository catalogue (fresh DB, `import_catalogue.py`) produced the identical projection, and Europe on the same snapshot is unchanged by both the hierarchy and the evidence-age decision (10 robots / 3 manufacturers, CURRENT). Under the old rule, Europe's three RobotShop K1 rows would have aged out about 2026-11-14; they now stay counted.

## 2. Production records relevant to North America (read-only, 2026-10-23)

| Robot | Record | Region | Status | Evidence (latest) | Treatment |
|---|---|---|---|---|---|
| unitree-g1 | robotshop-us, PURCHASE, USD 17,900 PUBLIC, lead_time_days 56 | US | AVAILABLE | 2026-08-17, MEDIUM, no human verification | **Qualifies** |
| 1x-neo | 1x-store, PURCHASE (USD 20,000) + SUBSCRIPTION (USD 499/month) | US | PREORDER | 2026-07-24, VERIFIED | **Qualifies** (preorder; USD 20,000 shown; the USD 499/month SUBSCRIPTION price has no matching offer, so it is not shown) |
| agility-digit | agility-raas, RAAS | US | ON_REQUEST | 2026-07-24, HIGH | **Qualifies** (RaaS; price not published). Its only evidence is the 2024 GXO announcement (see D4) |
| unitree-g1 / h1 / h2 / r1 | unitree-store | GLOBAL | various | 2026-07-24 … 09-26 | Global only, not regional |
| engineered-arts-ameca | engineered-arts-oem, RENTAL + PURCHASE | GLOBAL | AVAILABLE / ON_REQUEST | 2026-07-24 | Global only |
| 4ne1-mini | none, PURCHASE (two identical rows) | NULL | WAITLIST | 2026-10-02 | Unresolved region (governance-pinned; untouched) |

Deployments (shown separately; never establish purchasability): Agility Digit at GXO Logistics, US, production, since 2024-06-27; Figure 02 at BMW Group, US, completed. Apptronik Apollo at Mercedes-Benz has region NULL and is correctly **excluded**. Press reports place that pilot in Berlin-Marienfelde and Kecskemét, Hungary, so it is not a North American deployment. No Canada or Mexico offer exists in the catalogue.

## 3. Fresh source research (2026-10-23)

These sources were read by an agent under this work order. They are not owner-verified, and the confidence shown is the agent's assessment.

| Robot | Source | What it states | Use |
|---|---|---|---|
| 1x-neo | https://www.1x.tech/order (manufacturer) | "$20,000" Early Access (ownership); "$499/mo" (subscription); "$200 Deposit Due Today", "Fully Refundable"; "US Deliveries start 2026"; "Order Now". No other country named. | **Refresh the existing US offer and prices** (§4, batch NA-1) |
| agility-digit | https://agilityrobotics.com/ (manufacturer) | Contact-sales route only. No RaaS, purchase, price or country wording. | No refresh possible. The existing RaaS row's only evidence is the 2024 GXO deployment press release (owner decision D4). |
| unitree-g1 | https://robostore.com/products/unitree-g1-robotic-humanoid | RoboStore: "The Official US Distributor of Unitree". G1 Base "$17,990.00" (regular $21,600), USD. **"Sold Out - Notify me when it's available"**. Shipping policy: "primarily ships within the United States". | New provider and source. Needs owner authorization (A4); status mapping needs a decision. |
| unitree-g1-edu-plus-u2 | robostore.com, "G1 (U2) EDU Plus" | $53,900 USD (product page not opened) | Candidate; edition match and status unverified |
| unitree-r1-edu-* | robostore.com, "R1 … Starting at $8,990" | Edition not identified (R1 EDU U1–U6 exist in the catalogue) | Candidate; identity is ambiguous |
| softbank-nao | https://www.robotlab.com/store/nao/ (reseller and integrator) | "NAO V6 (NAO6) Standard Edition", "Starting at" "$16,990", "Purchase · Lease", "Get pricing & lead time", "US sales, setup & service". Not described as authorized. | New provider and source. Candidate (FROM price, ON_REQUEST status) |
| unitree-g1-edu-u3 | roboticscenter.ai (reseller) | $65,900 "Prices are for reference", US shipping estimate | Weak; not proposed |
| unitree (OEM store) | shop.unitree.com/policies/shipping-policy | Names no destination countries | Stays GLOBAL |
| Figure, Tesla, Apptronik, Boston Dynamics, Sanctuary | first-party sites | No buyer-facing order route found | None |
| Booster, Fourier, UBTECH, Galbot, Kepler, AgiBot, XPENG, PAL, Rainbow, Hanson, 1X EVE | — | **Not checked** in this pass. The reseller listings that appeared in search snippets were not fetched. | Open |

Not checked: RobotShop. It returns 403 to agents and must not be opened in the browser pane, so the G1 US row needs an **owner capture**.

**Geography:** UN M49 continental code **003 North America** = Northern America (021) + Caribbean (029) + Central America (013).
- The current UNSD page lists the 021 / 013 / 029 members but shows no 003 row.
- The composition is attested by the BCP 47 registration of region 003, which cites UN M.49: https://www.iana.org/assignments/lang-subtags-templates/003.txt.

## 4. Proposed HO-DATA Fast Lane batch (NOT applied; needs one explicit owner approval)

Price and availability are commercial assertions, so the standing Fast Lane policy does not pre-authorize them.

**Batch NA-1: refresh the existing 1X NEO US records.** It uses the existing provider `1x-store` and a manufacturer host.
- Scope: `db/catalogue/robots/1x-neo.json`. Append one evidence row to each of the 3 existing records: the PURCHASE/PREORDER offer, the PURCHASE price and the SUBSCRIPTION price.
- Nothing else changes: no status, price, region or provider change, and no new rows.

```json
{
  "source_url": "https://www.1x.tech/order",
  "source_type": "MANUFACTURER_STORE",
  "source_title": "1X — Order NEO",
  "excerpt": "<record-specific: '$20,000' | '$499/mo' | 'US Deliveries start 2026'; '$200 Deposit Due Today'>",
  "published_at": null,
  "observed_at": "2026-10-23",
  "verified_at": null,
  "confidence": "HIGH",
  "note": "RETRIEVAL: AGENT_ASSISTED_RESEARCH (docs/26) — retrieved 2026-10-23 by Claude (public GET, no login) in a session initiated by Robert Konecny, under owner work order 'HO-RESEARCH-NA-01 — Complete North America Research Resource' (2026-10-23). Not a MANUAL_BOOTSTRAP reading. Not human-verified. Page names US deliveries only; no other country."
}
```

This follows the existing convention for agent-retrieved commercial evidence in the catalogue:
- 9 manufacturer-store rows: `HIGH` / `MANUFACTURER_STORE`.
- 47 third-party rows: `MEDIUM` / `OTHER`.
- All of them have `verified_at` null. None is `VERIFIED`, and none is attributed to the owner.

**Expected production effect** (scoped import `--only 1x-neo`):
- Exactly 3 evidence_source rows added.
- NEO already counts under the 2026-10-23 rule. The batch moves its last-observed date from 2026-07-24 to 2026-10-23 and its displayed confidence to HIGH (the latest evidence decides confidence; never upgraded).
- The counts do not change: 3 robots / 3 manufacturers. **The gate still fails.**
- Re-observe before importing if the approval comes days later.
- Existing rows keep their VERIFIED 2026-07-24 evidence. Nothing is re-dated.

**Path to the 5 / 3 gate.** Each step needs its own owner decision. None of it is included in this PR.

| Step | Adds | Owner decision |
|---|---|---|
| Already counted (2026-10-23 rule) | unitree-g1, 1x-neo, agility-digit (3 robots / 3 manufacturers) | none |
| NA-1 (above) | newer last-observed date for 1x-neo; no count change | approve the batch |
| RoboStore as A4 source + provider `robostore-us` (DISTRIBUTOR) | unitree-g1-edu-plus-u2; possibly an R1 EDU edition; G1 Base only if "Sold Out" maps to an obtainable status | source authorization; edition matching; status mapping for "Sold Out - Notify me" (probably NOT obtainable) |
| RobotLAB as A4 source + provider (reseller and integrator) | softbank-nao (US, ON_REQUEST, FROM USD 16,990); this would be a 3rd manufacturer | source authorization; NAO manufacturer identity (Aldebaran / Maxtronics caveat) |

With RoboStore (G1 EDU U2) and RobotLAB (NAO), North America would reach **5 robots from 4 manufacturers and pass the gate**. That needs both source authorizations and confirmation that each listing is obtainable. Do **not** lower the threshold.

## 5. Owner decisions

- **D1 Geography (conflict to resolve).** This PR implements NORTH_AMERICA as all 41 UN M49 003 codes, **including territories** (PR, VI, GL, BM, KY, …), as the HO-RESEARCH-NA-01 brief asks.
  - This **differs from ADR-027 §4**, which reads "North America = US, CA, MX (+ NORTH_AMERICA row)", and from Europe v0.1, which covers sovereign states only.
  - The ADR is not edited here.
  - Today both readings give identical figures, because only US offers exist.
  - Choose one:
    - (a) keep M49 003 and amend ADR-027 §4; or
    - (b) restrict to US / CA / MX. That means a 3-code `regions.json` change plus `test_catalogue_regions_north_america.py` and the editorial paragraph 1.
- **D2 Hierarchy import.** `regions.json` adds NORTH_AMERICA and reparents the 41 codes. It changes only `region.parent_id`.
  - No offer, price or deployment references NORTH_AMERICA, so matching, lead routing and `commercial_offer` behave identically (pinned by a test).
  - It needs a governed production import of the regions. Until then the API returns 404 for North America, even with a preview token.
- **D3 Batch NA-1** (§4).
- **D4 Agility Digit RaaS row.** It now counts as a current North America offer. Its only evidence is the 2024 GXO announcement, and Agility's site today shows only a contact-sales route. Keep it, re-evidence it, or record it as non-current.
- **D5 New sources** RoboStore and RobotLAB (A4), with edition and status mapping.
- **D6 Editorial.** The North America fragment is DRAFT (`reviewed_at: null`) and is shown only in preview.
- **D7 Preview access.** `RESEARCH_PREVIEW_TOKEN` is unset everywhere. Setting it on both the API and the web app is needed to review on production.
- **D8 Publication.** Only after the gate passes in preview. `RESEARCH_PUBLISHED_REGIONS=europe,north-america` must be set in both places (Vercel API and Netlify web).
