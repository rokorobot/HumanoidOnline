// UseCaseTile — the whole-card use-case link used on both the /use-cases index
// and the homepage "Explore by use case" section. Live data only.
import Link from "next/link";

import { formatRobotCount } from "@/lib/format";
import type { UseCaseListItem } from "@/lib/types";
import { SystemLabel } from "./SystemLabel";

export function UseCaseTile({
  useCase,
  index,
}: {
  useCase: UseCaseListItem;
  index: number;
}) {
  return (
    <Link className="app" href={`/use-cases/${useCase.slug}`}>
      <SystemLabel>{String(index).padStart(2, "0")}</SystemLabel>
      <span className="name">{useCase.name}</span>
      <SystemLabel>{formatRobotCount(useCase.robot_count)}</SystemLabel>
    </Link>
  );
}
