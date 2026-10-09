// Primary nav link model, shared by SiteNav (interactive) and StaticNav (no client code).
// Kept free of client components so importing it never widens a route's client bundle.
import { researchNavVisible } from "@/lib/research";

export type NavSection =
  | "robots"
  | "compare"
  | "manufacturers"
  | "use-cases"
  | "research"
  | "about"
  | "find"
  | null;

const LINKS: { key: Exclude<NavSection, null>; href: string; label: string }[] = [
  { key: "robots", href: "/robots", label: "Robots" },
  { key: "compare", href: "/compare", label: "Compare" },
  { key: "manufacturers", href: "/manufacturers", label: "Manufacturers" },
  { key: "use-cases", href: "/use-cases", label: "Use Cases" },
  { key: "about", href: "/about", label: "About" },
];

// Research is part of the nav only while at least one Research Resource is
// published (RESEARCH_PUBLISHED_REGIONS); before that the nav is unchanged.
const RESEARCH_LINK = { key: "research" as const, href: "/research", label: "Research" };

export function primaryLinks() {
  if (!researchNavVisible()) return LINKS;
  const aboutAt = LINKS.findIndex((l) => l.key === "about");
  return [...LINKS.slice(0, aboutAt), RESEARCH_LINK, ...LINKS.slice(aboutAt)];
}

