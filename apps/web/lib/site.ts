/**
 * WS8.2 / R7 + R8 — the single authoritative canonical-origin resolver.
 *
 * Every machine surface derives its origin from here: JSON-LD `@id`/`url`
 * (AGENT-01.1), `sitemap.xml`, `robots.txt` and `llms.txt`. There is deliberately
 * one implementation — four independent ones would drift, and a staging deploy
 * emitting production canonicals is an SEO and correctness incident, not a
 * cosmetic bug.
 *
 * Gap B4: this module previously defaulted to `https://humanoidonline.com`, so
 * any preview or staging environment silently published production URLs. The
 * default is gone.
 *
 * Environment contract, mirroring `apps/api/app/config.py` and failing safe in
 * both directions (WS8-L5):
 *
 * - `APP_ENV` unset or empty -> production (strict). Never development.
 * - `APP_ENV` unrecognised   -> throws. A typo is loud.
 * - development / test       -> `http://localhost:3000` convenience default.
 * - staging / production     -> `NEXT_PUBLIC_SITE_URL` is REQUIRED and must be
 *   a syntactically valid absolute http(s) origin.
 */

export const ALLOWED_APP_ENVS = [
  "development",
  "test",
  "staging",
  "production",
] as const;

export type AppEnv = (typeof ALLOWED_APP_ENVS)[number];

/** Environments where a convenience origin may be assumed. */
const RELAXED_APP_ENVS: readonly string[] = ["development", "test"];

const DEVELOPMENT_SITE_URL = "http://localhost:3000";

export class ConfigurationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ConfigurationError";
  }
}

/** Resolve `APP_ENV`. Unset means production; unrecognised throws. */
export function resolveAppEnv(raw: string | undefined = process.env.APP_ENV): AppEnv {
  const value = (raw ?? "").trim();
  if (!value) return "production";
  const lowered = value.toLowerCase();
  if (!(ALLOWED_APP_ENVS as readonly string[]).includes(lowered)) {
    throw new ConfigurationError(
      `APP_ENV="${value}" is not a recognised environment. Use one of: ` +
        `${ALLOWED_APP_ENVS.join(", ")}. Leave it unset only if you intend production.`,
    );
  }
  return lowered as AppEnv;
}

/**
 * Validate a configured absolute origin. Exported so `lib/server.ts` reuses this
 * one implementation for `API_BASE_URL` — a second copy would be exactly the
 * drift this module warns about (and `lib/api.ts` was that drift, now removed).
 */
export function normalizeOrigin(raw: string, source: string): string {
  let parsed: URL;
  try {
    parsed = new URL(raw);
  } catch {
    throw new ConfigurationError(
      `${source}="${raw}" is not a valid absolute URL. ` +
        `Expected something like "https://humanoidonline.com".`,
    );
  }
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    throw new ConfigurationError(
      `${source}="${raw}" must use http or https (got "${parsed.protocol}").`,
    );
  }
  // An origin is scheme + host + port — no path, query or fragment. Accepting
  // "https://example.com/foo" and quietly folding the path into the canonical
  // base would emit subtly wrong canonical URLs everywhere; reject it instead
  // of normalising a value the operator did not mean.
  const hasPath = parsed.pathname !== "" && parsed.pathname !== "/";
  if (hasPath || parsed.search || parsed.hash) {
    throw new ConfigurationError(
      `${source}="${raw}" must be a bare origin (scheme + host + port) with no ` +
        `path, query or fragment. Use "${parsed.origin}".`,
    );
  }
  return parsed.origin;
}

/**
 * The canonical origin for this deployment.
 *
 * Resolved per call rather than captured at module load so that a build does
 * not bake in one environment's answer, and so tests can exercise the contract.
 * `next.config.mjs` runs the same check at build time, which is where a
 * misconfigured production deploy should fail — loudly, before it serves.
 */
export function siteUrl(): string {
  const env = resolveAppEnv();
  const configured = (process.env.NEXT_PUBLIC_SITE_URL ?? "").trim();

  if (configured) return normalizeOrigin(configured, "NEXT_PUBLIC_SITE_URL");

  if (RELAXED_APP_ENVS.includes(env)) return DEVELOPMENT_SITE_URL;

  throw new ConfigurationError(
    `NEXT_PUBLIC_SITE_URL is required when APP_ENV="${env}". Refusing to fall ` +
      "back to a hard-coded production hostname: a staging or preview deploy " +
      "must never publish production canonical URLs. Set NEXT_PUBLIC_SITE_URL " +
      "to this environment's own origin.",
  );
}

/** Absolute canonical URL for a site-relative path (pass-through for absolute). */
export function absoluteUrl(path: string): string {
  if (/^https?:\/\//i.test(path)) return path;
  return `${siteUrl()}/${path.replace(/^\/+/, "")}`;
}
