# HO-RESEARCH-NA-01 / NA-02 — North America Research Resource: evidence, readiness and the commercial-data batch

**Date:** 2026-10-23 · **Status:** review package. Nothing is published, nothing is written to production, and no publication flag is changed.
**Resource:** `/research/humanoid-availability/north-america` (+ `.json`). Same ADR-027 read model, gate, JSON-LD, sitemap rule and preview session as Europe.
**PR:** rokorobot/HumanoidOnline#200 (draft).

## 1. Verdict

| | Production today (read-only) | After the NA-02 batch (local rehearsal) |
|---|---|---|
| Published robots (population) | 43 | 43 |
| Robots with a qualifying North America offer | 3 | **5** |
| Manufacturers with a qualifying offer | 3 | **5** |
| Launch gate (5 robots / 3 manufacturers, unchanged) | fails (3 < 5) | **passes** |
| Publication health | LIMITED_EVIDENCE | CURRENT |
| Groups reconcile | yes | yes (5 + 1 + 4 + 13 + 20 = 43) |
| Europe | 10 robots / 3 manufacturers | unchanged |

- **Production today:** Unitree G1, 1X NEO and Agility Digit.
- **After the batch:** + Booster K1 Educational and NAO.

**Technically ready, data not yet in production.** The page, JSON, JSON-LD, preview, sitemap gate and tests are complete. Publication still needs the owner decisions in §9: approving the batch, importing it, reviewing the editorial text and switching the publication flag.

**Evidence-age rule (owner decision 2026-10-23, ADR-027 §12 amended).** An offer and its price stay current until newer evidence replaces them. Age alone never removes an offer, and every row shows its last-observed date. The abandoned 90-day window no longer applies anywhere in this resource.

## 2. Qualifying offers after the batch (snapshot 2026-10-23)

| Robot (edition) | Manufacturer of record | Seller (type) | Region | Transaction | Status | Price | Last observed | Confidence | Source |
|---|---|---|---|---|---|---|---|---|---|
| Unitree G1 (G1 Basic) | Unitree | RobotShop US (distributor) | US | Purchase | AVAILABLE | USD 17,900 | 2026-08-17 | MEDIUM | robotshop.com G1 listing (owner capture) |
| 1X NEO | 1X Technologies | 1X store (OEM) | US | Purchase | PREORDER | USD 20,000 | 2026-07-24 | VERIFIED | 1x.tech NEO page |
| Agility Digit (generation-unspecified; see §4) | Agility Robotics | Agility (RaaS provider) | US | RaaS | ON_REQUEST | not published | 2026-10-23 | HIGH | agilityrobotics.com/sales + 2024 GXO release |
| **Booster K1 Educational** (K1 EDU, SKU RB-Boo-10) | Booster Robotics | RobotShop US (distributor) | US | Purchase | ON_REQUEST ("Special order") | USD 15,699 | 2026-10-23 | MEDIUM | robotshop.com K1 EDU listing |
| **NAO** (NAO6; NAO V6 Standard Edition) | SoftBank Robotics | RobotLAB (integrator) | US | Purchase | ON_REQUEST (quote) | from USD 16,990 | 2026-10-23 | MEDIUM | robotlab.com/store/nao/ |
| NAO (same robot, counted once) | SoftBank Robotics | RobotLAB (integrator) | US | Lease (RaaS leasing) | ON_REQUEST | not published | 2026-10-23 | MEDIUM | robotlab.com/store/nao/ |

**Other groups:**
- Global-only (not counted): Ameca, Unitree H1, H2 and R1.
- Unresolved region: 4NE1 Mini (governance-pinned, untouched).

**Deployments (shown separately; never counted as offers):**
- Digit at GXO Logistics, US, production, since 2024-06-27. Per Agility, this is Digit 4.
- Figure 02 at BMW, US, completed.
- Apptronik Apollo at Mercedes-Benz has no recorded region, so it is excluded. Press places that pilot in Berlin and in Kecskemét, Hungary.

**Canada and Mexico:** no confirmed offer for either country is on file. Every qualifying offer is US-scoped.

## 3. Candidate offers investigated (NA-02)

All retrievals were made 2026-10-23 by Claude (WebFetch), under the owner work order HO-RESEARCH-NA-02, which names these URLs. They are agent observations, not human-verified, and none sets `verified_at`.

### A. Booster K1 Educational, RobotShop US — CONFIRMED, proposed

**Source:** https://www.robotshop.com/products/booster-robotics-k1-educational-humanoid-robot
- RobotShop answers plain requests with HTTP 403.
- WebFetch received RobotShop's own agent-facing product summary: its cart links carry `ref=ai-md`, and it states "Data as of: 2026-10-14T00:23:35Z (UTC)". No block was circumvented.

**What the listing states:**
- "Price: 15699.00 USD"
- "Availability: Special order"
- "Add to cart" and "Checkout directly"
- "Customs, inspection, and prep handled locally before shipment"
- No lead time

**Edition match:**
- "K1 EDU Robot by Booster Robotics", "Jetson Orin NX 8GB, 117 TOPS AI computing power" and "approx. 80 minutes (5Ah battery) at 0.4 m/s" are the `booster-k1-educational` configuration.
- It is the same SKU, RB-Boo-10, as the existing RobotShop EU offer.

**How it is recorded:**
- **Status ON_REQUEST, not AVAILABLE.** It is a special-order item. The mapping follows the same SKU's RobotShop EU "On Demand" offer (ON_REQUEST, "not held in standing stock"). It is not described as immediate stock.
- **Price:** PUBLIC USD 15,699. `price_basis` is left unknown because the agent-facing summary does not say whether tariffs, tax or shipping are included.
  - The owner's preliminary note says "US tariff-inclusive". That was not confirmed in this retrieval, so it is not recorded.
- **Provider:** the existing `robotshop-us` is reused.

**Not reconciled:**
- The owner's preliminary note quotes "On Demand" wording and a tariff-inclusive price. The agent-facing summary says "Special order" and is silent on tariffs.
- An owner capture of the human-facing page would settle the wording and the price basis. It would not change the status mapping.

### B. NAO V6, RobotLAB — CONFIRMED, proposed (needs a new provider)

**Source:** https://www.robotlab.com/store/nao/

**What the page states:**
- "NAO V6 (NAO6) Standard Edition"
- "Starting at $16,990", "Purchase Price $16,990", "RobotLAB sells the NAO V6 Standard Edition for $16,990"
- "Purchase · Lease"; "RobotLAB also offers Robot-as-a-Service (RaaS) leasing and financing"
- "Get pricing & lead time"; quote and demo forms only, with no cart
- "US sales, setup & service"; "Sold, deployed, and serviced nationwide by RobotLAB"
- RobotLAB describes itself as "a reseller and integrator" and does not claim to be authorized.

**Identity:**
- `softbank-nao` is NAO6 by owner ruling DEC-04. The manufacturer of record stays SoftBank Robotics.
- The page's spec table names "SoftBank Robotics / Aldebaran". Its product metadata says "Manufacturer: RobotLAB", which is a conflict and is not used. Maxtronics, the current NAO6 publisher, is not mentioned.
- Counted under manufacturer of record `softbank-robotics`.

**How it is recorded:**
- PURCHASE ON_REQUEST, priced as **FROM** USD 16,990 with basis "NAO V6 Standard Edition purchase price … taxes, shipping and services not stated".
- LEASE ON_REQUEST, with no price.
- These are two offers on one robot, and the robot is counted once (tested).

**Source authorization and provider registration:**
- Retrieval rests on the NA-02 work order (docs/26 A3, as amended by R5).
- `robotlab` is a **new provider row** (INTEGRATOR, US). Registering it is part of the batch approval.
- A4 owner authorization applies only if RobotLAB is to be *monitored* by the discovery pipeline. That is not proposed.

### Rejected or held

| Candidate | Decision | Why |
|---|---|---|
| RoboStore, Unitree G1 EDU Plus (U2) | **Not recorded** (documented non-qualifying candidate) | The seller lists the G1 range as "Sold Out - Notify me". RoboStore's "Official US Distributor of Unitree" claim is self-declared. Revisit only on a listing that can be ordered. |
| RoboStore, G1 Base | Not recorded | "Sold Out - Notify me"; unitree-g1 already qualifies through RobotShop US |
| Robotics Center, G1 EDU U3 | Not recorded | "Prices are for reference"; reseller authority unknown; no catalogue edition decision for U3 |
| 1X NEO refresh (1x.tech/order, 2026-10-23) | Optional, not in the batch | NEO already counts. A newer HIGH row would replace the VERIFIED 2026-07-24 row as the confidence shown. |

## 4. Digit 4 / Digit 5 reconciliation

**What Agility says:**
- **2026-09-15 release** ("Agility Unveils Digit 5…"):
  - "Digit 4 has logged more than 65,000 hours of operational time".
  - Digit 4 works "across numerous customer sites in North America, including GXO, Schaeffler, Amazon".
  - "Early access to Digit 5 is expected to begin in the first half of 2027", with general availability "by the end of 2027". It also mentions "more than $300 million in multi-year customer orders for Digit 5 subject to … contractual milestones".
- **/solutions/digit-5:** "Digit 5 is in development and the features, specifications, capabilities, and designs shown are subject to change." The specifications are marked preliminary.
- **2026-10-22 release** ("…as It Prepares Digit 5 for Commercial Scale"):
  - Repeats early access in H1 2027 and general availability by end-2027.
  - Says Digit is "commercially deployed today".
- **/sales** ("Get Digit in your facility"): reached from both "Deploy Digit" and "Deploy Digit 5" buttons. It names no generation, transaction type, price or country.

**What each catalogue fact represents:**

| `agility-digit` fact | Generation | Basis |
|---|---|---|
| height 175 cm, weight 65 kg, payload 16 kg (owner-ratified 2026-08-18); 28 DoF (Agility article 2024-10-31) | **Digit 4** (pre-Digit-5 deployed generation) | Dates and values predate Digit 5. Digit 5 states 23 kg payload. |
| GXO deployment (2024-06-27, RaaS) and the GXO commercial-status evidence | **Digit 4** | Agility, 2026-09-15 |
| Variant `digit-v5` "Digit (current gen)" (created 2026-07-24) | **Digit 4**, despite the slug | Created before Digit 5 existed. "v5" did not mean Digit 5. |
| US ON_REQUEST offer with /sales evidence (D4) | **Generation-unspecified** | The page is generation-neutral. The offer note now says so. RAAS and US scope rest on the 2024 GXO contract (Digit 4). |

**Applied in this PR:** only the offer note, which states the history, the current channel and the generation boundary. Digit stays listed (D4). No Digit 5 specification or availability is attributed to this record.

**Proposed for owner review (D10, not applied):** the smallest identity-safe correction.
- Keep `agility-digit` as the Digit 4 / deployed-generation record. Keep its slug and stable IDs.
- Rename the variant's display name from "Digit (current gen)" to "Digit 4 (deployed generation)". Keep the slug `digit-v5`: it is a stable ID referenced by `test_importer_stable_ids.py` and `docs/04`.
- Later, if wanted, add Digit 5 as a **new unpublished** record through the governed identity process, holding its preliminary specs and its "early access H1 2027" status.

## 5. US regulatory finding (FCC Covered List)

**Primary sources.** The fact sheet was read directly. The Public Notices were read in full by a research agent, and their content is consistent with the fact sheet.
- **FCC fact sheet DOC-423682A1 (2026-07-28):**
  - The Covered List now includes "advanced robotic devices (defined as mobile robots, such as humanoids and quadrupeds)" produced in foreign countries, "regardless of the nationality of origin".
  - "Covered equipment is banned from receiving new equipment authorizations."
  - The action "does not prohibit the import, sale, or use of any existing models … the FCC previously authorized" and "does not affect any previously purchased devices".
  - Department of War Conditional Approvals exempt devices.
- **Public Notice DA 26-786 (2026-07-28):** adds "Foreign-produced advanced robotic devices, except advanced robotic devices which have been granted a Conditional Approval by DoW". Coverage is "identified by place of production, not by entity". The definition covers humanoid robots, with exclusions for drones, vehicles, fixed industrial robots and medical devices.
- **Conditional Approvals since:**
  - DA 26-996 (2026-09-18): Husqvarna, ANSCER.
  - DA 26-1114 (2026-10-16): Matic, Volley.
  - DA 26-1130 (2026-10-21): Vulcan.
  - No humanoid maker in the catalogue is named.

**The four cases:**
- **(a) A seller listing a product.** Not regulated by these documents as such. The fact sheet says retailers may continue to sell previously authorized models.
- **(b) A previously authorized model.** It can still be imported, sold and used. This is an FCC fact-sheet statement; the codified rule text was not located.
- **(c) A new model.** It cannot obtain new equipment authorization if it is foreign-produced, unless Conditional Approval applies. Newly produced units of an already-authorized model are **not addressed** in the documents read.
- **(d) Conditional Approval.** Granted by the Department of War to named models (above), subject to an onshoring plan and vetting.

**Effect on the article:**
- A neutral DRAFT editorial paragraph with five citations was added. It states the rule, the previously-authorized carve-out and the per-model nature of the question.
- It does not say any robot is or is not authorized, compliant, illegal or unavailable.
- The catalogue's commercial status and offers are unchanged by it.

**Not verified:** model-specific FCC IDs (for example, search snippets about Unitree authorizations) were not checked and are not used.

## 6. Proposed HO-DATA Fast Lane batch HO-RESEARCH-NA-02 (one approval; NOT applied)

These are commercial assertions (price and availability), so the batch needs one explicit owner approval. That approval covers the merge, the rehearsal on a Neon branch of production, the guarded production import and its verification.

| # | Change | File |
|---|---|---|
| 1 | NORTH_AMERICA continent + 41 members reparented (D1/D2) | `db/catalogue/regions.json` |
| 2 | New provider `robotlab` (INTEGRATOR, US) | `db/catalogue/providers.json` |
| 3 | `booster-k1-educational`: + US PURCHASE ON_REQUEST offer (robotshop-us, "Special order") + PUBLIC USD 15,699 price; 2 evidence rows (MEDIUM, `OTHER`, RETRIEVAL note, published_at 2026-10-14 = the seller's data timestamp, observed_at 2026-10-23) | `db/catalogue/robots/booster-k1-educational.json` |
| 4 | `softbank-nao`: + US PURCHASE ON_REQUEST + US LEASE ON_REQUEST offers (robotlab) + FROM USD 16,990 price; 3 evidence rows (MEDIUM, `OTHER`, RETRIEVAL note) | `db/catalogue/robots/softbank-nao.json` |
| 5 | `agility-digit`: D4 contact-sales evidence (1 row, HIGH, `MANUFACTURER_SITE`), seller wording, generation-explicit note | `db/catalogue/robots/agility-digit.json` |

**Exact expected changes.** Manifest: `db/catalogue/ho_research_na02_expected.json`, 54 entries / 57 changes.
- region: +1 added, 41 changed (parent)
- provider: +1
- availability_offer: +4 added, 1 removed (the Digit row is replaced because its note changed)
- pricing_offer: +2
- evidence_source: +6
- robot: 1 changed. This is `softbank-nao`, whose trigger-derived `lowest_purchase_price` becomes 16,990 USD, so NAO now shows a "from" price on catalogue listings.

**Rehearsed locally:**
- Disposable Postgres: `main` catalogue, then this branch.
- `import_preflight.py --manifest` gave **PREFLIGHT PASS: every business change is accounted for**.
- The re-import is idempotent (0 changes).
- The projection from that database matches §1.

**Import mode:** a **full** `import_catalogue.py`, not `--only`. A scoped run pulls only the regions its robots reference plus their ancestors, so it would reparent the US alone and leave North America with 2 member regions instead of 42. Production drift, if any, would surface in the rehearsal preflight as an unexplained change and stop the import.

**Expected research effect:**
- North America goes from 3 robots / 3 manufacturers to **5 / 5**; the gate passes and health is CURRENT.
- Europe is unchanged. Its K1 EDU row stays an EU RobotShop offer; the new US row is a separate offer that counts only for North America.

## 7. SEO / GEO changes in this round

**Buyer FAQs.** Four new FAQs are generated from the governed projection, so they are shared with Europe and change automatically with the data:
- direct order versus quote, preorder or contact sales;
- manufacturer versus third-party seller;
- which countries have a confirmed offer;
- whether a deployment means a robot can be bought.

This brings the FAQ, and the FAQPage JSON-LD, to 8 questions.

**DRAFT editorial (North America):**
- geography (UN M49 003);
- seller types;
- ordering stages (available, limited, special order, preorder, contact sales);
- deployments versus offers;
- the FCC caveat.

It cites five sources, and every source is now rendered, not only the first. It contains no hard-coded price, count or status.

**Display fixes:**
- A FROM price shows as "From 16,990 USD".
- The key-figure row shows "RaaS" with its original capitalisation.

## 8. Geography: implemented grouping vs ADR-027 §4 wording

- **Implemented:** `NORTH_AMERICA` = the 41 UN M49 003 codes, including territories, each a direct child.
- **ADR-027 §4 currently reads:** "North America = US, CA, MX (+ NORTH_AMERICA row)".
- **Proposed replacement for §4.** This is a proposal for owner approval only, not approved:

> North America = the `NORTH_AMERICA` continent row and its direct children: the UN M49 North America grouping (003 = Northern America 021 + Central America 013 + Caribbean 029), i.e. Canada, Mexico, the United States and the Central American and Caribbean countries and territories that have an ISO 3166-1 row (41 codes). Unlike Europe v0.1, territories are included. An offer counts only for the country its seller documents.

## 9. Owner decisions remaining

1. **D1 Geography.** Approve the §8 ADR wording, or restrict to US / CA / MX. Today's figures are identical either way.
2. **Batch NA-02 (§6).** One approval covering:
   - the regions import (D2);
   - the `robotlab` provider registration;
   - the K1 EDU and NAO offers;
   - the Digit D4 evidence;
   - the full-import mode.
3. **D10 Digit identity (§4).** Rename the variant display name; optionally add Digit 5 as a new unpublished record later.
4. **D11 Status mapping.** RobotShop US G1 "On Demand" is recorded AVAILABLE, while K1 "Special order" and K1 EU "On Demand" are ON_REQUEST. Keep this inconsistency, or align G1 in a separate batch.
5. **D6 Editorial.** Review the DRAFT North America fragment, including the FCC paragraph. Then set `reviewed_at` and `reviewed_by`.
6. **D7 Preview.** Set `RESEARCH_PREVIEW_TOKEN` on the Vercel API and on Netlify web to review on production after the import.
7. **D8 Publication.** Only after the production preview shows the gate passing: `RESEARCH_PUBLISHED_REGIONS=europe,north-america` on both.
8. **Optional owner capture** of the RobotShop K1 EDU human-facing page, for the "On Demand" and tariff wording.
