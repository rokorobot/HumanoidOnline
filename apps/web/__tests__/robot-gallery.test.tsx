/**
 * WS8.4 / R20 — the missing-image empty state, as a component test.
 *
 * The verified catalogue ships 7/7 images, so this §5.2 state ("IMAGE
 * UNAVAILABLE", never a placeholder fill) is not reachable through the full-
 * catalogue e2e. It is proven here at the component level instead: an empty
 * image set renders the governed unavailable state with an accessible name, and
 * never a fabricated placeholder image.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { RobotGallery } from "../components/RobotGallery";

describe("RobotGallery — missing image (R20 §5.2)", () => {
  // globals:false -> no auto-cleanup; unmount between tests so DOM doesn't leak.
  afterEach(cleanup);

  it("renders IMAGE UNAVAILABLE with an accessible name, not a placeholder", () => {
    const { container } = render(<RobotGallery robotName="Test Bot" images={[]} />);

    expect(screen.getByText("IMAGE UNAVAILABLE")).toBeTruthy();
    // Accessible name states the reason, tied to the specific robot.
    const region = screen.getByRole("img", {
      name: /No verified image available for Test Bot/i,
    });
    expect(region).toBeTruthy();
    // Never a real <img> placeholder fill — absence of a verified image must not
    // be papered over with stock/generated art (MEDIA-01 + §5.2).
    expect(container.querySelector("img")).toBeNull();
  });

  it("renders the gallery when a verified image is present", () => {
    render(
      <RobotGallery
        robotName="Test Bot"
        images={[
          {
            image_url: "https://example.test/g1.jpg",
            image_type: "FRONT",
            source_name: "Unitree",
            source_url: null,
            source_type: "MANUFACTURER",
            is_official: true,
            is_primary: true,
            attribution: null,
          },
        ]}
      />,
    );
    expect(screen.queryByText("IMAGE UNAVAILABLE")).toBeNull();
  });
});

describe("RobotGallery — representative image disclosure (MEDIA-01 §4)", () => {
  afterEach(cleanup);

  const representative = {
    image_url: "https://example.test/r1.png",
    image_type: "FRONT",
    source_name: "QUADRUPED Robotics",
    source_url: null,
    source_type: "DISTRIBUTOR",
    is_official: false,
    is_primary: true,
    attribution: "© QUADRUPED Robotics UG",
    is_representative: true,
    representative_note: "Representative R1 image; EDU appearance and equipment may vary.",
  };

  it("labels a stand-in and shows its note, never a bare Verified ✓", () => {
    const { container } = render(
      <RobotGallery robotName="R1 EDU U1" images={[representative]} />,
    );

    // Queried by class, not by text: "Representative" now appears in the badge,
    // in the note and in the section heading, so a text query is ambiguous by
    // construction — which is itself evidence the disclosure is present.
    const badge = container.querySelector(".ro-imgbadge");
    expect(badge).toBeTruthy();
    expect(badge!.className).toContain("ro-imgbadge--rep");
    expect(badge!.textContent).toBe("Representative");
    // The exact-edition claim must be absent, not merely outweighed.
    expect(screen.queryByText("Verified ✓")).toBeNull();
    expect(screen.queryByText("Official ✓")).toBeNull();
    expect(
      screen.getByText("Representative R1 image; EDU appearance and equipment may vary."),
    ).toBeTruthy();
  });

  it("does not call a gallery of stand-ins VERIFIED", () => {
    render(<RobotGallery robotName="R1 EDU U1" images={[representative]} />);
    expect(screen.getByText("IDENTITY IMAGERY — REPRESENTATIVE")).toBeTruthy();
    expect(screen.queryByText("IDENTITY IMAGERY — VERIFIED")).toBeNull();
  });

  it("states official provenance alongside the label rather than dropping it", () => {
    render(
      <RobotGallery
        robotName="R1 EDU U1"
        images={[{ ...representative, is_official: true }]}
      />,
    );
    expect(screen.getByText("Representative · Official ✓")).toBeTruthy();
  });

  it("still discloses when the note is missing", () => {
    const { representative_note: _omitted, ...noNote } = representative;
    render(<RobotGallery robotName="R1 EDU U1" images={[noNote]} />);
    expect(
      screen.getByText("Representative image — may not depict this exact edition."),
    ).toBeTruthy();
  });

  const verified = {
    image_url: "https://example.test/g1.jpg",
    image_type: "FRONT",
    source_name: "Unitree",
    source_url: null,
    source_type: "MANUFACTURER",
    is_official: true,
    is_primary: true,
    attribution: null,
    is_representative: false,
    representative_note: null,
  };

  it("gives a MIXED gallery a neutral heading, claiming neither of the whole set", () => {
    render(
      <RobotGallery
        robotName="R1 EDU U1"
        images={[verified, { ...representative, is_primary: false }]}
      />,
    );
    // Neither claim is true of the set, so neither is made.
    expect(screen.getByText("IDENTITY IMAGERY")).toBeTruthy();
    expect(screen.queryByText("IDENTITY IMAGERY — VERIFIED")).toBeNull();
    expect(screen.queryByText("IDENTITY IMAGERY — REPRESENTATIVE")).toBeNull();
  });

  it("keeps per-image labels in a mixed gallery when the stand-in is not primary", () => {
    const { container } = render(
      <RobotGallery
        robotName="R1 EDU U1"
        images={[verified, { ...representative, is_primary: false }]}
      />,
    );
    // The exact-edition primary keeps its own true label...
    expect(container.querySelector(".ro-imgbadge")!.textContent).toBe("Official ✓");
    // ...and the stand-in, which has no caption of its own in the strip, still
    // discloses through its accessible name and tooltip.
    const thumb = container.querySelector(".ro-gallery__strip img")!;
    expect(thumb.getAttribute("alt")).toContain("(representative image)");
    expect(thumb.getAttribute("title")).toContain("EDU appearance and equipment may vary");
  });

  it("keeps the note on a mixed gallery whose primary IS the stand-in", () => {
    const { container } = render(
      <RobotGallery
        robotName="R1 EDU U1"
        images={[representative, { ...verified, is_primary: false }]}
      />,
    );
    expect(screen.getByText("IDENTITY IMAGERY")).toBeTruthy();
    expect(container.querySelector(".ro-imgbadge")!.className).toContain("ro-imgbadge--rep");
    expect(
      screen.getByText("Representative R1 image; EDU appearance and equipment may vary."),
    ).toBeTruthy();
  });

  it("leaves a genuinely verified image untouched", () => {
    render(
      <RobotGallery
        robotName="Test Bot"
        images={[
          {
            image_url: "https://example.test/g1.jpg",
            image_type: "FRONT",
            source_name: "Unitree",
            source_url: null,
            source_type: "MANUFACTURER",
            is_official: true,
            is_primary: true,
            attribution: null,
            is_representative: false,
            representative_note: null,
          },
        ]}
      />,
    );
    expect(screen.getByText("Official ✓")).toBeTruthy();
    expect(screen.getByText("IDENTITY IMAGERY — VERIFIED")).toBeTruthy();
    expect(document.querySelector(".ro-imgnote")).toBeNull();
  });
});
