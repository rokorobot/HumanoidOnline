# DR-C1 — Master catalogue vs public catalogue: robot records are never removed

| | |
|---|---|
| **Status** | **DECIDED — ADOPTED, 2026-08-16, Robert Konecny (product owner)** |
| **Raised** | 2026-08-16, following a live incident |
| **Decision owner** | Robert Konecny (product owner) — sole ratifying authority |
| **Applies to** | `db/import_catalogue.py`, `db/catalogue_entries.py`, `db/catalogue/**`, every surface that reads `robot.is_published` |
| **Related** | `docs/09_MEDIA_CONTRACT.md` (MEDIA-01 imagery), `docs/10_AGENT_CONTRACT.md` §01.7 (machine surfaces expose published canonical only) |

This record captures **what happened, what was decided, and what is deliberately
left open**. It is the source for the catalogue invariants below.

## 1. The incident

A routine `db/import_catalogue.py` run was executed to verify three newly
authored Booster K1 entries. The catalogue page immediately afterwards showed
**7 robots where it had shown 43**.

Nothing was deleted. All 46 robot rows were intact throughout; only the
`is_published` flag had been reset on 39 of them. That is precisely what made it
dangerous — the loss was invisible in the data and visible only in the browser,
and it presented exactly as though records had been erased.

**Mechanism.** `import_robot()` listed `is_published` among the columns written
by its `ON CONFLICT (slug) DO UPDATE SET` clause. Identity-only entries created
by `catalogue_entries.py stubs` are authored with `"is_published": false`. So an
editorial decision to display those robots — made directly against the database —
was silently reverted by the next fact refresh.

**Root cause, stated plainly:** the importer treated editorial visibility as
disposable, importer-controlled data.

## 2. Decision — catalogue invariants

Adopted as permanent policy:

1. **Robot records are never deleted** merely because they are sparse,
   discontinued, pre-production, unavailable, or lacking images. The
   historical/master catalogue is **cumulative**.
2. **Catalogue visibility is a separate editorial decision.** A robot may be
   *stored but not currently displayed*.
3. **`is_published` is not importer-controlled data.** A routine catalogue
   import must never silently change public visibility.
4. **Image availability must never determine the existence of a robot record.**
   Richly documented profiles (Unitree, Booster) and image-less sparse records
   belong to the same underlying catalogue. Improving the former creates no
   pressure whatsoever to remove the latter.
5. **Production lifecycle should eventually be represented separately** — for
   example `announced`, `prototype`, `pre_production`, `in_production`,
   `discontinued`, `historical` — rather than encoding all of it in
   `is_published`.
6. **Until the public-display policy is formally defined, no agent may
   independently decide** that pre-production or discontinued robots should
   disappear.

### Two clean concepts

| | |
|---|---|
| **Master catalogue** | everything we know about — cumulative, never reduced |
| **Public catalogue** | the currently approved *view* of the master catalogue |

A store of 46 robots displaying 42, 39, 30 or another number later is
**perfectly legitimate**, once a display policy says so. What is **not**
legitimate is 46 stored records becoming 7 because an import, a media check or a
UI change discarded or hid them.

## 3. What was implemented

`db/import_catalogue.py`:

* `EDITORIAL_COLUMNS = ("is_published",)` — named explicitly, so widening the
  protected set is a deliberate edit rather than an accident.
* `is_published` is written **on INSERT** (a brand-new row has no editorial
  history to protect) and **held back on UPDATE**. Catalogue facts — name,
  summary, specs, commercial status, manufacturer — still refresh on every run.
* `--apply-publication-state` opts in to rewriting visibility from JSON. It is a
  **publishing operation, not a fact refresh**, and it announces itself in the
  output.
* Every import prints `Catalogue state: N stored, M displayed.` so a surprising
  gap surfaces at the moment it appears rather than being found later in a
  browser.

`apps/api/tests/test_catalogue_publication_state.py` pins the invariant: a
routine import must not emit `is_published` in its UPDATE clause, must still
refresh the facts, and an explicit publishing operation must still be able to
move visibility. The tests need no database, so they cannot be skipped into
uselessness.

## 4. Deliberately left open

* **The public-display policy itself.** Which lifecycle states appear in the
  public catalogue is the product owner's decision and is not made here.
* **A `production_status` / lifecycle enum** (invariant 5). Recorded as the
  intended direction; not yet designed, migrated, or scheduled.
* **The 39 stub robots' publication state** currently lives only in the
  database, not in the JSON. It now survives imports, but it is not yet
  reproducible from a clean bootstrap. Resolving that belongs with the display
  policy, since it is the same question: what should the public catalogue show?
