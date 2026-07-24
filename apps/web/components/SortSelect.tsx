"use client";

// SortSelect — updates the `sort` URL param, preserving all active filters.
import { useRouter } from "next/navigation";

import { asArray, asString, type RawSearchParams } from "@/lib/search-params";

const OPTIONS: { value: string; label: string }[] = [
  { value: "name", label: "Name A→Z" },
  { value: "price", label: "Price ↑" },
  { value: "-price", label: "Price ↓" },
  { value: "-payload", label: "Payload ↓" },
  { value: "-newest", label: "Newest" },
];

export function SortSelect({ params }: { params: RawSearchParams }) {
  const router = useRouter();
  const current = asString(params.sort) ?? "name";

  function onChange(e: React.ChangeEvent<HTMLSelectElement>) {
    const usp = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) {
      if (k === "sort") continue;
      for (const item of asArray(v)) if (item !== "") usp.append(k, item);
    }
    usp.set("sort", e.target.value);
    router.push(`/robots?${usp.toString()}`, { scroll: false });
  }

  return (
    <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
      <label className="ho-syslabel" htmlFor="sortsel">
        Sort
      </label>
      <select
        id="sortsel"
        className="sortsel"
        aria-label="Sort results"
        value={current}
        onChange={onChange}
      >
        {OPTIONS.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </div>
  );
}
