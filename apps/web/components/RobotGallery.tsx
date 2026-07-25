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
            // No verified image of this exact robot has cleared identity and rights.
          </span>
        </div>
      </div>
    );
  }

  const primary = images[0];
  const rest = images.slice(1);

  return (
    <div className="ro-gallery">
      <SectionIndex>IDENTITY IMAGERY — VERIFIED</SectionIndex>
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
          <span className="ro-imgbadge">
            {primary.is_official ? "Official ✓" : "Verified ✓"}
          </span>
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
        <ul className="ro-gallery__strip" aria-label="More verified images">
          {rest.map((img, i) => (
            <li key={i}>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={img.image_url}
                alt={`${robotName} — ${img.image_type.toLowerCase()}`}
                title={img.source_name ?? undefined}
                loading="lazy"
              />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
