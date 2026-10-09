"use client";

// (client component: its markup is then delivered once, as HTML, instead of again in the RSC payload)
// SearchBox - the catalogue search field (UX-02A). A plain GET form: it works without JS and
// sends ONLY the buyer's raw text as `q`. The server interprets `q` on every render, so the URL
// stays the single source of truth (refresh / back / forward restore everything).
export function SearchBox({ q }: { q: string }) {
  return (
    <form className="searchbar searchbar--page" role="search">
      <input
        type="search"
        name="q"
        defaultValue={q}
        placeholder="e.g. warehouse robot under EUR 20000"
        aria-label="Search robots"
      />
      <button type="submit">Search</button>
    </form>
  );
}
