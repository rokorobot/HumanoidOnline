// Primary nav link model for server components (SiteNav, StaticNav). Pure data lives in
// nav-model.ts; this adds the server-side research flag. No client components here.
import { researchNavVisible } from "@/lib/research";

import { linksFor } from "./nav-model";

export type { NavSection } from "./nav-model";

export function primaryLinks() {
  return linksFor(researchNavVisible());
}
