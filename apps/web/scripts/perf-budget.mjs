// WS8.6 / R24 (Part A) — deterministic bundle-weight budgets.
//
// A pre-production, fully reproducible performance gate: it inspects the built
// `.next` output and asserts the gzipped First Load JS of each key route (and
// the shared baseline) stays within budget. No server, no timing, no CPU/LCP
// thresholds — same source in => same bytes out, so it never flakes.
//
// Part B (e2e/perf-budget.spec.ts) complements this by measuring the ACTUAL
// served routes (document bytes + JS assets) against the fixed catalogue.
//
// Budgets were measured from the baseline at `main @ 2b9cd53` and frozen with
// ~15% headroom. To re-baseline after an intentional change, run
// `node scripts/perf-budget.mjs --report` and update the numbers below.
import { gzipSync } from "node:zlib";
import { readFileSync, statSync } from "node:fs";
import { join } from "node:path";

const NEXT_DIR = ".next";
const MANIFEST = join(NEXT_DIR, "app-build-manifest.json");

// route manifest key -> { label, budgetKB }. Budgets are gzipped First Load JS.
// Baseline (gzip, main @ 2b9cd53) is noted for each; budget ~= baseline * 1.15.
const ROUTE_BUDGETS = {
  "/page": { label: "/", budgetKB: 120 }, //               baseline 103.6
  "/robots/page": { label: "/robots", budgetKB: 122 }, //  baseline 105.7
  "/robots/[slug]/page": { label: "/robots/[slug]", budgetKB: 122 }, // 106.0
  "/compare/page": { label: "/compare", budgetKB: 128 }, // baseline 111.1
  "/find-a-humanoid/page": { label: "/find-a-humanoid", budgetKB: 125 }, // 108.5
  "/matches/[id]/page": { label: "/matches/[id]", budgetKB: 124 }, // 107.1
};
const SHARED_BUDGET_KB = 116; // baseline 100.1

const report = process.argv.includes("--report");

function gzipKB(file) {
  return gzipSync(readFileSync(join(NEXT_DIR, file)), { level: 9 }).length / 1024;
}

let manifest;
try {
  manifest = JSON.parse(readFileSync(MANIFEST, "utf8"));
  statSync(join(NEXT_DIR, "app-build-manifest.json"));
} catch {
  console.error(
    `perf-budget: ${MANIFEST} not found. Run \`npm run build\` first.`,
  );
  process.exit(2);
}

const pages = manifest.pages ?? {};
// Shared baseline = the chunks common to every app page (loaded on every route).
const pageKeys = Object.keys(pages).filter((k) => k.endsWith("/page"));
let shared = null;
for (const k of pageKeys) {
  const s = new Set(pages[k]);
  shared = shared === null ? s : new Set([...shared].filter((x) => s.has(x)));
}
const sharedKB = [...(shared ?? [])].reduce((a, f) => a + gzipKB(f), 0);

const failures = [];
const rows = [];

function check(label, actualKB, budgetKB) {
  const ok = actualKB <= budgetKB;
  rows.push(
    `${ok ? "ok " : "OVER"}  ${label.padEnd(20)} ${actualKB
      .toFixed(1)
      .padStart(7)} kB  (budget ${budgetKB} kB)`,
  );
  if (!ok) {
    failures.push(
      `${label}: ${actualKB.toFixed(1)} kB exceeds budget ${budgetKB} kB`,
    );
  }
}

check("shared baseline", sharedKB, SHARED_BUDGET_KB);
for (const [key, { label, budgetKB }] of Object.entries(ROUTE_BUDGETS)) {
  const files = pages[key];
  if (!files) {
    failures.push(`${label}: route "${key}" missing from build manifest`);
    continue;
  }
  check(label, files.reduce((a, f) => a + gzipKB(f), 0), budgetKB);
}

console.log("WS8.6 / R24 (A) — bundle budgets (gzipped First Load JS)");
console.log(rows.join("\n"));

if (report) process.exit(0);
if (failures.length) {
  console.error(`\nperf-budget FAILED:\n  ${failures.join("\n  ")}`);
  process.exit(1);
}
console.log("\nperf-budget: all routes within budget.");
