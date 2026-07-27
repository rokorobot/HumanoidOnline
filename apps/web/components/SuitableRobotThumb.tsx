// SuitableRobotThumb — MEDIA-01 governed thumbnail for the use-case "suitable
// robots" ranked list. Renders ONLY the display-eligible primary image the API
// already filtered (identity VERIFIED + rights cleared); when none exists it
// renders the explicit IMAGE UNAVAILABLE state — never a generated, look-alike,
// or placeholder fill (docs/09_MEDIA_CONTRACT.md). Same image truth + gate as the
// catalogue RobotCard and Robot Detail, just the compact inline size for a row.
//
// The image also links to the robot detail; the robot NAME remains the primary
// clickable link in the row itself.
import Link from "next/link";

import type { RobotImagePrimary } from "@/lib/types";

export function SuitableRobotThumb({
  slug,
  name,
  image,
}: {
  slug: string;
  name: string;
  image?: RobotImagePrimary | null;
}) {
  return (
    <Link className="fit-thumb" href={`/robots/${slug}`}>
      {image ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img className="fit-thumb__img" src={image.image_url} alt={name} loading="lazy" />
      ) : (
        // Absence is stated, never papered over — the accessible name gives the
        // reason, tied to the specific robot (MEDIA-01 §5.2).
        <span
          className="fit-thumb__unavailable"
          role="img"
          aria-label={`No verified image available for ${name}`}
        >
          IMAGE UNAVAILABLE
        </span>
      )}
    </Link>
  );
}
