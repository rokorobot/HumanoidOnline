// Pure nav link model (no imports): safe to use from client components, so the
// mobile menu can build its list itself instead of receiving it as RSC props.
export type NavSection =
  | "robots"
  | "compare"
  | "manufacturers"
  | "use-cases"
  | "research"
  | "about"
  | "find"
  | null;

export const LINKS: { key: Exclude<NavSection, null>; href: string; label: string }[] = [
  { key: "robots", href: "/robots", label: "Robots" },
  { key: "compare", href: "/compare", label: "Compare" },
  { key: "manufacturers", href: "/manufacturers", label: "Manufacturers" },
  { key: "use-cases", href: "/use-cases", label: "Use Cases" },
  { key: "about", href: "/about", label: "About" },
];

// Research is part of the nav only while at least one Research Resource is
// published (RESEARCH_PUBLISHED_REGIONS); before that the nav is unchanged.
export const RESEARCH_LINK = { key: "research" as const, href: "/research", label: "Research" };

export function linksFor(research: boolean) {
  if (!research) return LINKS;
  const aboutAt = LINKS.findIndex((l) => l.key === "about");
  return [...LINKS.slice(0, aboutAt), RESEARCH_LINK, ...LINKS.slice(aboutAt)];
}

export interface MenuLink {
  key: string;
  href: string;
  label: string;
  current?: boolean;
  cta?: boolean;
}

export function menuLinksFor(active: NavSection, research: boolean): MenuLink[] {
  return [
    ...linksFor(research).map((l) => ({
      key: l.key,
      href: l.href,
      label: l.label,
      current: active === l.key,
    })),
    { key: "find", href: "/find-a-humanoid", label: "Find a Humanoid", current: active === "find", cta: true },
  ];
}
