// ADR-027 Step 3 — the Europe Regional Research Resource (HTML). The gate,
// metadata and rendering are shared with every region (components/ResearchRegionPage).
import { researchRegionRoute } from "@/components/ResearchRegionPage";

export const dynamic = "force-dynamic";

const { generateMetadata, ResearchRegionPage } = researchRegionRoute("europe");

export { generateMetadata };
export default ResearchRegionPage;
