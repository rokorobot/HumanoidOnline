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
