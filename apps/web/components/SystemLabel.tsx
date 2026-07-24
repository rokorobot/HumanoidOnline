// SystemLabel (§6.1) — the technical field/kicker label. Uppercase MACHINE
// text; a label, never a data value itself.
import type { ReactNode } from "react";

export function SystemLabel({
  children,
  as: Tag = "span",
  className = "",
}: {
  children: ReactNode;
  as?: "span" | "div" | "legend" | "dt";
  className?: string;
}) {
  return <Tag className={`ho-syslabel ${className}`.trim()}>{children}</Tag>;
}
