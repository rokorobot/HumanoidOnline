// ============================================================================
// WS4 — Saved comparison views. DEVICE-LOCAL localStorage ONLY.
// ----------------------------------------------------------------------------
// HARD BOUNDARY: no server persistence, no account/user model, no API, no
// schema change. A saved view is just a named pointer at a canonical /compare
// URL on THIS device. Selecting a save reconstructs that URL. Invalid or stale
// local data must fail safely (be ignored/skipped), never crash the page.
// ============================================================================

export const SAVED_VIEWS_KEY = "ho.compare.savedViews.v1";
/** Bumped if the stored shape changes; unknown versions are skipped, not crashed. */
export const SAVED_VIEW_VERSION = 1 as const;

export interface SavedView {
  name: string;
  created_at: string; // ISO 8601
  version: number;
  /** Canonical, self-contained compare URL, e.g. "/compare?ids=a,b&ref=a&units=imperial&view=evidence". */
  url: string;
}

function hasStorage(): boolean {
  try {
    return typeof window !== "undefined" && !!window.localStorage;
  } catch {
    return false;
  }
}

/** True only for a well-formed SavedView pointing at a /compare URL of this version. */
function isValidView(v: unknown): v is SavedView {
  if (v === null || typeof v !== "object") return false;
  const o = v as Record<string, unknown>;
  return (
    typeof o.name === "string" &&
    o.name.trim().length > 0 &&
    typeof o.created_at === "string" &&
    typeof o.version === "number" &&
    o.version === SAVED_VIEW_VERSION &&
    typeof o.url === "string" &&
    o.url.startsWith("/compare?")
  );
}

/**
 * Read all valid saved views. Malformed JSON, non-array payloads, and individual
 * bad/stale entries are silently dropped — a corrupt store never throws.
 */
export function loadSavedViews(): SavedView[] {
  if (!hasStorage()) return [];
  let raw: string | null = null;
  try {
    raw = window.localStorage.getItem(SAVED_VIEWS_KEY);
  } catch {
    return [];
  }
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(isValidView);
  } catch {
    // Corrupt JSON — fail safe: behave as if there are no saved views.
    return [];
  }
}

function persist(views: SavedView[]): void {
  if (!hasStorage()) return;
  try {
    window.localStorage.setItem(SAVED_VIEWS_KEY, JSON.stringify(views));
  } catch {
    // Quota / disabled storage — degrade silently. State stays in the URL.
  }
}

/**
 * Save (or replace, by name) a view for the given canonical URL. Returns the new
 * list. A blank name or non-/compare URL is rejected (returns the current list).
 */
export function saveView(name: string, url: string): SavedView[] {
  const clean = name.trim();
  if (!clean || !url.startsWith("/compare?")) return loadSavedViews();
  const view: SavedView = {
    name: clean,
    created_at: new Date().toISOString(),
    version: SAVED_VIEW_VERSION,
    url,
  };
  const existing = loadSavedViews().filter((v) => v.name !== clean);
  const next = [view, ...existing];
  persist(next);
  return next;
}

/** Delete a saved view by name. Returns the new list. */
export function deleteView(name: string): SavedView[] {
  const next = loadSavedViews().filter((v) => v.name !== name);
  persist(next);
  return next;
}
