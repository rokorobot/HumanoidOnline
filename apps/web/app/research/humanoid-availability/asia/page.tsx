// HO-RESEARCH-ASIA-01 — the Asia Regional Research Resource (HTML): the
// same governed projection, gate and rendering as Europe
// (components/ResearchRegionPage). Closed until RESEARCH_PUBLISHED_REGIONS lists
// "asia".
import { researchRegionRoute } from "@/components/ResearchRegionPage";

export const dynamic = "force-dynamic";

const { generateMetadata, ResearchRegionPage } = researchRegionRoute("asia");

export { generateMetadata };
export default ResearchRegionPage;
