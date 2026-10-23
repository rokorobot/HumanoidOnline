// HO-RESEARCH-NA-01 — the North America Regional Research Resource (HTML): the
// same governed projection, gate and rendering as Europe
// (components/ResearchRegionPage). Closed until RESEARCH_PUBLISHED_REGIONS lists
// "north-america".
import { researchRegionRoute } from "@/components/ResearchRegionPage";

export const dynamic = "force-dynamic";

const { generateMetadata, ResearchRegionPage } = researchRegionRoute("north-america");

export { generateMetadata };
export default ResearchRegionPage;
