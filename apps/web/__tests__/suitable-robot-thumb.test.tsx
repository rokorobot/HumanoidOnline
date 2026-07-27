/**
 * MEDIA-01 governed thumbnail on the use-case "suitable robots" ranked list.
 *
 * The eligibility gate itself lives on the backend (is_display_eligible); the API
 * hands the frontend either a display-eligible primary image or null. These tests
 * prove the row faithfully renders that governed result: a real verified image
 * when present, and the explicit IMAGE UNAVAILABLE state (never a fabricated /
 * placeholder fill) when there is none — so no unverified image can appear here.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { SuitableRobotThumb } from "../components/SuitableRobotThumb";

describe("SuitableRobotThumb — MEDIA-01 governed row thumbnail", () => {
  afterEach(cleanup);

  it("renders IMAGE UNAVAILABLE with an accessible name, not a placeholder, when there is no eligible image", () => {
    const { container } = render(
      <SuitableRobotThumb slug="test-bot" name="Test Bot" image={null} />,
    );

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

  it("renders the governed verified image when the API supplies one", () => {
    const { container } = render(
      <SuitableRobotThumb
        slug="test-bot"
        name="Test Bot"
        image={{
          image_url: "https://example.test/front.jpg",
          source_name: "Unitree",
          is_official: true,
        }}
      />,
    );

    expect(screen.queryByText("IMAGE UNAVAILABLE")).toBeNull();
    const img = container.querySelector("img");
    expect(img?.getAttribute("src")).toBe("https://example.test/front.jpg");
    expect(img?.getAttribute("alt")).toBe("Test Bot");
  });

  it("links the thumbnail to the robot detail (name remains the primary link in the row)", () => {
    const { container } = render(
      <SuitableRobotThumb slug="test-bot" name="Test Bot" image={null} />,
    );
    const link = container.querySelector("a.fit-thumb");
    expect(link?.getAttribute("href")).toBe("/robots/test-bot");
  });
});
