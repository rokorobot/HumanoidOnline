# apps/web — HumanoidOnline frontend (WS1 foundation)

Next.js (App Router) + TypeScript. Vitest + React Testing Library.

WS1 scope: an executable app shell plus the test/typecheck/build harness. No
product UI and no visual design (deliberately deferred — see the NON-GOAL in the
WS1 brief). Next.js renders; FastAPI decides (02_ARCHITECTURE.md rule 2).

## Prerequisites

- Node.js 20+ and npm.

## Install & run

```bash
cd apps/web
npm ci            # or `npm install` on first setup
npm run dev       # http://localhost:3000
```

## Verify (same checks CI runs)

```bash
npm run typecheck   # tsc --noEmit
npm run test        # vitest run
npm run build       # next build
```

Configure the backend URL via `NEXT_PUBLIC_API_BASE_URL` (see `.env.example`).
