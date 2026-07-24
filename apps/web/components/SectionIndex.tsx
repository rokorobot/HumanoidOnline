// SectionIndex (§6.2) — ordinal section marker + editorial wayfinding.
// Clean production form: "NN — TITLE" (no discipline-gradient chrome, §5.2).
import type { ReactNode } from "react";

export function SectionIndex({ children }: { children: ReactNode }) {
  return <span className="ho-section-index">{children}</span>;
}
