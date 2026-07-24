# tests/

Cross-cutting / end-to-end tests that span the frontend and backend together.

Unit and component tests live **beside their code**:

- Backend: `apps/api/tests/` (pytest)
- Frontend: `apps/web/__tests__/` (Vitest + React Testing Library)
- Database: `db/bootstrap.py` + `db/validate.py`, exercised by CI

WS1 establishes no e2e suite yet (there is no product journey to drive — the app
is an infrastructure shell). Full-journey e2e arrives with the product
workstreams and the acceptance criteria in `docs/05_ACCEPTANCE_CRITERIA.md`.
