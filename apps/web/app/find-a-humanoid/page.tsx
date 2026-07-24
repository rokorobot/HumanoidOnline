// Find a Humanoid — WS5 Buyer Intent. Productionized as the real 12-step
// requirement wizard that persists ONE buyer_requirement (POST
// /api/buyer-requirements). No matching, no lead capture, no contact fields, no
// auth — those are later workstreams. The TASK step is seeded from the live
// use-case catalogue; the COUNTRY step from the live canonical region list;
// /find-a-humanoid?use_case=<slug> pre-selects a use case.
import { SectionIndex } from "@/components/SectionIndex";
import { SiteFooter, SiteNav } from "@/components/SiteNav";
import { SystemHeader } from "@/components/SystemHeader";
import { listRegions, listUseCases } from "@/lib/api-client";

import { Wizard } from "./Wizard";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Find a Humanoid — HumanoidOnline",
};

export default async function FindAHumanoidPage({
  searchParams,
}: {
  searchParams: Promise<{ use_case?: string }>;
}) {
  const sp = await searchParams;
  const [useCasesPage, countries] = await Promise.all([
    listUseCases({ limit: 100 }),
    listRegions({ type: "COUNTRY" }),
  ]);
  const useCases = useCasesPage.items;
  // Pre-seed only when the slug resolves to a real, live use case.
  const seedUseCase =
    sp.use_case && useCases.some((u) => u.slug === sp.use_case)
      ? sp.use_case
      : null;

  return (
    <>
      <SystemHeader
        title="REQUIREMENT WIZARD / BUYER INTENT"
        fields={[
          { label: "FLOW", value: "12 STEPS" },
          { label: "CAPTURES", value: "BUYER REQUIREMENT" },
        ]}
      />
      <div className="wrap wrap--narrow">
        <SiteNav active="find" />

        <div className="pagebar">
          <div>
            <SectionIndex>FIND A HUMANOID / GUIDED REQUIREMENT CAPTURE</SectionIndex>
            <h1>Find a humanoid</h1>
          </div>
        </div>

        <p className="prose" style={{ maxWidth: "60ch", marginBottom: "var(--ho-sp-4)" }}>
          Answer as much or as little as you know. <strong>Unknown</strong> and{" "}
          <strong>Skip</strong> are both first-class answers — they are recorded as
          distinct signals and never invent data you did not give.
        </p>

        <Wizard
          useCases={useCases}
          countries={countries}
          seedUseCase={seedUseCase}
        />
      </div>
      <SiteFooter />
    </>
  );
}
