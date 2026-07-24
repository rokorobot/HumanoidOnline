import { defineConfig, devices } from "@playwright/test";

// Production-like integration gate. Proves the frontend renders the VERIFIED
// WS2B catalogue (not seed, not mock). The full chain — fresh Postgres ->
// db/schema.sql -> import_catalogue.py -> FastAPI -> Next (built) -> Playwright
// — is orchestrated by the `web-integration` CI job and the local instructions
// in apps/web/README.
//
// - WEB_BASE_URL: if set, tests run against that already-running server and
//   Playwright starts nothing (used locally / when the chain is wired by hand).
// - Otherwise Playwright starts `next start` itself (expects `next build` done
//   and the API reachable at API_BASE_URL).
const WEB_BASE_URL = process.env.WEB_BASE_URL;
const PORT = Number(process.env.WEB_PORT ?? 3000);
const baseURL = WEB_BASE_URL ?? `http://127.0.0.1:${PORT}`;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL,
    trace: "on-first-retry",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
  webServer: WEB_BASE_URL
    ? undefined
    : {
        command: `npx next start -p ${PORT}`,
        url: baseURL,
        reuseExistingServer: !process.env.CI,
        timeout: 120_000,
        env: {
          API_BASE_URL: process.env.API_BASE_URL ?? "http://127.0.0.1:8000",
        },
      },
});
