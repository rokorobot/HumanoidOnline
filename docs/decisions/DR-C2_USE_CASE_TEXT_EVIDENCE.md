# DR-C2 — Use-case text with factual claims: interim evidence, then `USE_CASE` evidence rows

**Status:** APPROVED — 2026-11-02, product owner.
**Related:** AGENTS.md rule 7, HO-CONTENT-01 (`docs/audit/HO-CONTENT-01_THIN_CONTENT_ENRICHMENT_2026-11.md`, PR #235), `db/schema.sql` `evidence_source`.

## 1. Problem

HO-CONTENT-01 adds factual claims to use-case `description`, `typical_requirements` and `key_limitations`: named deployments (Agility Digit at GXO), orders (UBTECH Walker S2), published figures (Figure 02 at BMW Spartanburg). AGENTS rule 7 requires deployment claims to keep linked evidence. `evidence_source.subject_type` has no use-case subject, so these sources can only be recorded in the review doc.

## 2. Decision

1. **Interim (accepted):** HO-CONTENT-01 use-case text may ship with its sources recorded per claim in the HO-CONTENT-01 review doc. This is the only exception; it covers the text in PR #235 and nothing added later.
2. **Next schema change (approved):** use-case text gets database evidence. Implementation: add `USE_CASE` to the `evidence_subject` enum and record rows in `evidence_source` with `claim_fields` naming the supported use-case fields, as manufacturer evidence already does. This replaces the "`use_case_source` table" in the HO-CONTENT-01 proposal: same outcome, one existing table instead of a new one (AGENTS rule 10).
3. Once that change lands, the HO-CONTENT-01 sources move from the review doc into `db/catalogue/use_cases.json` evidence rows. From then on no use-case factual claim lands without one.
