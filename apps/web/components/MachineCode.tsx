// MachineCode (§6.3) — render a system identifier (model_code / slug) as a
// boxed asset-tag chip. Optionally links to the canonical record.
import Link from "next/link";
import type { ReactNode } from "react";

export function MachineCode({
  children,
  href,
  inverted = false,
}: {
  children: ReactNode;
  href?: string;
  inverted?: boolean;
}) {
  const cls = inverted ? "ho-code ho-chip--inv" : "ho-code";
  if (href) {
    return (
      <Link className={cls} href={href}>
        {children}
      </Link>
    );
  }
  return <span className={cls}>{children}</span>;
}
