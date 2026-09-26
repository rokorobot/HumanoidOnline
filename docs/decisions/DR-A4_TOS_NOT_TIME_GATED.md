# DR-A4 — Terms of Service: an owner-recorded decision, not a time-gated review

| | |
|---|---|
| **Status** | **DECIDED — ADOPTED, 2026-09-26, Robert Konecny (product owner)** |
| **Decision owner** | Robert Konecny (product owner) — sole ratifying authority |
| **Amends** | `docs/16` LIVE.2 (terms validity), §5 (review expiry / refusal semantics), §19 Gates A and B (terms expiry / page-hash); `docs/11` DATA-D1.9 (clarified, not weakened); `docs/21` §2 requirement 3 and `docs/22` Phase 3.1 (freshness ToS-expiry check) |
| **Unchanged** | robots.txt enforcement in full (LIVE.2 robots rules, Gate B robots rules); LIVE.3 no circumvention; the DATA-D1 boundary (no canonical writes, no auto-VERIFIED, human promotion only) |
| **Schema** | None. `ck_discovery_source_eligible` and `DiscoverySource.radar_eligible` are unchanged. |

## Decision

1. **The owner reads each source's Terms of Service personally** and records the
   result in `discovery_source.tos_status`. That recorded decision remains part of
   radar eligibility exactly as before: `radar_eligible` and the database CHECK
   still require `tos_status = 'ALLOWED'` for an enabled source.
2. **That decision does not expire and is not machine-revalidated.** Automated
   acquisition (discovery acquisition, Stage A readiness, Stage B runs) and
   scheduled freshness must **not** block, halt or degrade because:
   - `tos_expires_at` is missing or in the past;
   - `tos_reviewed_at` is missing or old;
   - `tos_page_hash` is missing or has changed;
   - no recent review row exists in `source_eligibility_review`.
3. **No Terms-of-Service page is fetched or re-fetched** by any automated process
   to determine eligibility. No ToS hash-invalidation and no ToS-expiry gate is
   implemented. Revisiting a decision is an owner act: change `tos_status`.
4. The `tos_*` columns and `source_eligibility_review` rows remain as
   informational provenance (what was read, when, by whom). They gate nothing
   beyond `tos_status` itself.
5. **robots.txt remains mandatory and unchanged**: stored `robots_status` must
   not be a disallow; robots is re-read at the start of every run and evaluated
   per URL (≤ 24 h cache); a disallow blocks the URL, halts the run
   (`HALTED_BY_POLICY`) and disables the source pending re-review, as docs/16
   LIVE.2 and Gate B already require. A robots restriction and a ToS decision are
   different policies; this record changes only the latter's currency rules.

## Why

The 90-day expiry, page-hash invalidation and automated re-fetch of legal pages
turned a one-time owner judgement into a recurring machine gate that no one had
built and that would silently disable sources for reasons unrelated to what the
owner decided. The owner prefers to make the terms judgement personally, once per
source, and revisit it deliberately.

## Where the old text lives

The superseded text in `docs/16`, `docs/21` and `docs/22` is **kept, not deleted**,
and each place carries an inline "Amended by DR-A4" note pointing here. Where the
old text and this record disagree, **this record governs**.

## Implementation (Stage A amendment, PR #64)

- `app/services/discovery/eligibility.py` — shared source/URL acquisition policy:
  `radar_eligible` + approved host (`homepage_url`) + `allowed_path_prefixes`.
  Never reads `tos_expires_at`, `tos_reviewed_at` or `tos_page_hash`.
- `app/services/freshness/eligibility.py` — the `tos_expires_at` check removed;
  the 24 h robots-recency ceiling kept.
- Tests pin both halves: ToS currency never blocks; `tos_status` other than
  `ALLOWED` and robots disallow still do.
