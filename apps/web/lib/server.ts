/**
 * WS8.7 / WS8-L5 — the server-side FastAPI base URL, resolved fail-closed.
 *
 * Server Components and the two route handlers reach the knowledge API through
 * this. `API_BASE_URL` is server-only and never shipped to the client.
 *
 * Gap found while binding the real production topology: this module previously
 * fell through to `http://localhost:8000` whenever `API_BASE_URL` (or the old
 * `NEXT_PUBLIC_API_BASE_URL` alias) was absent. In production that is a silent
 * development fallback — precisely what WS8-L5 forbids: a misconfigured deploy
 * would quietly point at localhost instead of failing loudly.
 *
 * Environment contract, mirroring `lib/site.ts` and `apps/api/app/config.py`:
 *
 * - `APP_ENV` unset or empty -> production (strict). Never development.
 * - `APP_ENV` unrecognised   -> throws (via `resolveAppEnv`). A typo is loud.
 * - development / test       -> `http://localhost:8000` convenience default.
 * - staging / production     -> **`API_BASE_URL` is REQUIRED** and must be a
 *   valid absolute http(s) origin.
 *
 * `NEXT_PUBLIC_API_BASE_URL` is deliberately **not** an alternate production
 * path. Next.js is the web-facing tier; the browser never needs an API origin,
 * so there is exactly one authoritative server-side knob.
 *
 * Resolution is lazy (a function, not a module-level constant) for the same
 * reason `siteUrl()` is: the standalone `next build` job compiles with
 * `APP_ENV` unset — i.e. production — and must not have to supply a runtime API
 * URL merely to typecheck and bundle. The check belongs at request time, where
 * a misconfigured deploy should fail.
 */
import { ConfigurationError, normalizeOrigin, resolveAppEnv } from "./site";

/** Environments where a convenience API origin may be assumed. */
const RELAXED_APP_ENVS: readonly string[] = ["development", "test"];

const DEVELOPMENT_API_BASE_URL = "http://localhost:8000";

/** The FastAPI origin for this deployment. Throws rather than guessing. */
export function apiBaseUrl(): string {
  const env = resolveAppEnv();
  const configured = (process.env.API_BASE_URL ?? "").trim();

  if (configured) return normalizeOrigin(configured, "API_BASE_URL");

  if (RELAXED_APP_ENVS.includes(env)) return DEVELOPMENT_API_BASE_URL;

  throw new ConfigurationError(
    `API_BASE_URL is required when APP_ENV="${env}". Refusing to fall back to ` +
      `"${DEVELOPMENT_API_BASE_URL}": a production or staging deployment that ` +
      "silently targets localhost fails every governed read instead of saying " +
      "why. Set API_BASE_URL to this environment's FastAPI origin (for example " +
      'the internal service address "http://api:8000").',
  );
}
