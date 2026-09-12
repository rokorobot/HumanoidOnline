// MEDIA-01 verified-image gallery for Robot Detail. Renders ONLY display-eligible
// real images (the API already filters to identity VERIFIED + rights cleared), each
// with provenance (Official/Verified + Source + attribution). When there is no
// eligible image it renders the explicit IMAGE_UNAVAILABLE state — never a
// generated, look-alike, or placeholder fill (docs/09_MEDIA_CONTRACT.md).
//
// Presentation-fidelity only (MEDIA-01.6): the design system frames/sizes the real
// photo; it never redraws, generates, or transforms the robot.
import { GraphicMarker } from "@/components/GraphicMarker";
import { SectionIndex } from "@/components/SectionIndex";
import type { RobotImage } from "@/lib/types";

export function RobotGallery({
  robotName,
  images,
}: {
  robotName: string;
  images: RobotImage[];
}) {
  if (images.length === 0) {
    return (
      <div className="ro-gallery">
        <SectionIndex>IDENTITY IMAGERY</SectionIndex>
        <div className="ro-unavailable" role="img" aria-label={`No verified image available for ${robotName}`}>
          <GraphicMarker />
          <span className="ro-unavailable__label">IMAGE UNAVAILABLE</span>
          <span className="ro-unavailable__note">
            {"// No verified image of this exact robot has cleared identity and rights."}
          </span>
        </div>
      </div>
    );
  }

  const primary = images[0];
  const rest = images.slice(1);
  // The section heading is a claim about the whole SET, so it has three honest
  // states. "VERIFIED" must not be asserted of a set containing a stand-in, and
  // "REPRESENTATIVE" must not be asserted of exact-edition imagery. A mixed
  // gallery therefore gets a neutral heading, and the per-image badges and notes
  // carry the distinction where it actually applies.
  const representativeCount = images.filter((i) => i.is_representative).length;
  const sectionHeading =
    representativeCount === 0
      ? "IDENTITY IMAGERY — VERIFIED"
      : representativeCount === images.length
        ? "IDENTITY IMAGERY — REPRESENTATIVE"
        : "IDENTITY IMAGERY";

  return (
    <div className="ro-gallery">
      <SectionIndex>{sectionHeading}</SectionIndex>
      <figure className="ro-gallery__figure ho-cropframe">
        <span className="ho-crop" aria-hidden="true" />
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          className="ro-gallery__img"
          src={primary.image_url}
          alt={`${robotName} — ${primary.image_type.toLowerCase()}`}
          loading="lazy"
        />
        <figcaption className="ro-gallery__cap">
          {/* What makes a line/chassis image honest: the caption says what is
              actually shown, so it is never read as this exact edition. A
              stand-in never claims "Official ✓" or a bare "Verified ✓" — but a
              genuine official/verified provenance is not erased either, it is
              stated ALONGSIDE the representative label, because both facts are
              true and dropping either one misinforms. */}
          <span
            className={
              primary.is_representative ? "ro-imgbadge ro-imgbadge--rep" : "ro-imgbadge"
            }
          >
            {primary.is_representative
              ? primary.is_official
                ? "Representative · Official ✓"
                : "Representative"
              : primary.is_official
                ? "Official ✓"
                : "Verified ✓"}
          </span>
          {/* The note is what makes the label mean something. A representative
              image with no note reaching the page would be an unlabelled
              stand-in, so the designation alone is still surfaced. */}
          {primary.is_representative && (
            <span className="ro-imgnote">
              {primary.representative_note ??
                "Representative image — may not depict this exact edition."}
            </span>
          )}
          {primary.source_name && (
            <span className="ro-imgsrc">
              Source:{" "}
              {primary.source_url ? (
                <a href={primary.source_url} target="_blank" rel="noreferrer noopener">
                  {primary.source_name}
                </a>
              ) : (
                primary.source_name
              )}
            </span>
          )}
          {primary.attribution && (
            <span className="ro-imgattr">{primary.attribution}</span>
          )}
        </figcaption>
      </figure>

      {rest.length > 0 && (
        <ul className="ro-gallery__strip" aria-label="More images">
          {rest.map((img, i) => (
            <li key={i}>
              {/* A stand-in in the strip carries its disclosure too: the
                  accessible name and tooltip say so, since these thumbnails
                  have no caption of their own. */}
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={img.image_url}
                alt={
                  img.is_representative
                    ? `${robotName} — ${img.image_type.toLowerCase()} (representative image)`
                    : `${robotName} — ${img.image_type.toLowerCase()}`
                }
                title={
                  img.is_representative
                    ? [img.representative_note, img.source_name]
                        .filter(Boolean)
                        .join(" — ") || undefined
                    : (img.source_name ?? undefined)
                }
                loading="lazy"
              />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
