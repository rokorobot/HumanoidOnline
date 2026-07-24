# AGENTS.md — Operating rules for coding agents on HumanoidOnline

These rules are binding for any autonomous or semi-autonomous coding agent working in this repository. They exist because the product contract, not the agent, owns product-level decisions.

**Before starting a new workstream, read [`docs/08_DEVELOPMENT_ROADMAP.md`](docs/08_DEVELOPMENT_ROADMAP.md).** The roadmap controls delivery sequencing; frozen product contracts remain authoritative.

1. **Do not alter product scope without explicit approval.** Scope is `docs/01_PRODUCT_CONTRACT.md`. If a task seems to require scope change, stop and ask.

2. **The PostgreSQL DDL is the canonical data model.** `db/schema.sql` wins over ORM models, API shapes, and UI assumptions. Schema changes are their own reviewed change, never a side effect.

3. **Do not remove dormant Phase 3–5 structures** (`provider`, `transaction_type` values, offer views, lead-routing tables, dormant fields) merely because MVP v0.1 does not use them. They are deliberate.

4. **Do not introduce infrastructure not required by the Product Contract.** No microservices, Kubernetes, Elasticsearch, event buses, vector databases, or new services "for later."

5. **Every implementation task lands with tests.** Matching-engine work: pytest against fixtures. API work: endpoint tests. UI work: at least the journey it serves (see `docs/05_ACCEPTANCE_CRITERIA.md`).

6. **Unknown data must remain UNKNOWN.** Never fabricate, infer, or default commercial facts. NULL never becomes 0, false, "not available", or a made-up price. This applies to code, seeds, and fixtures.

7. **Evidence-linked fields must preserve provenance.** Writes to price, availability, commercial status, deployment claims or regional availability keep or create their `evidence_source` linkage. No commercial fact without evidence.

8. **Keep matching deterministic and independently testable.** A pure function; no I/O, no randomness, no LLM in the scoring path. Identical input → identical output, always.

9. **Do not implement purchase, rental, or leasing transaction workflows in v0.1.** Lead capture (`commercial_lead`) is the only commercial action. No checkout, booking, payments, or escrow.

10. **Prefer simple, maintainable implementation over cleverness.** Boring and readable beats abstract and general. When in doubt, choose the solution a future maintainer will understand in one read.
