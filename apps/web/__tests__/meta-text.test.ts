// SEO-03 — title and meta-description length discipline.
import { describe, expect, it } from "vitest";

import { DESCRIPTION_MAX, DESCRIPTION_MIN, fitDescription, fitTitle } from "../lib/meta-text";

const EXTRA = "Compare the humanoid robots suited to home use, ranked by fit, with availability and evidence.";

describe("fitDescription", () => {
  it("keeps an in-range description unchanged", () => {
    const d = "Humanoid-robot manufacturers tracked by HumanoidOnline, with their verified platforms.";
    expect(fitDescription(d, EXTRA)).toBe(d);
  });

  it("tops up a short description with the page-specific sentence", () => {
    const out = fitDescription("Domestic assistance and companionship.", EXTRA);
    expect(out).toBe(`Domestic assistance and companionship. ${EXTRA}`.slice(0, out.length));
    expect(out.length).toBeGreaterThanOrEqual(DESCRIPTION_MIN);
    expect(out.length).toBeLessThanOrEqual(DESCRIPTION_MAX);
  });

  it("uses the extra sentence when there is no description", () => {
    expect(fitDescription(null, EXTRA)).toBe(EXTRA);
  });

  it("cuts a long description at whole sentences", () => {
    const long =
      "As of 2026-10-24, HumanoidOnline lists 2 published humanoid robots with a confirmed offer in Asia. " +
      "1 can be purchased: 1 on request. Additionally, 1 of these robots has a confirmed rental offer.";
    expect(fitDescription(long, EXTRA)).toBe(
      "As of 2026-10-24, HumanoidOnline lists 2 published humanoid robots with a confirmed offer in Asia. 1 can be purchased: 1 on request.",
    );
  });

  it("cuts one over-long sentence at a word boundary with an ellipsis", () => {
    const out = fitDescription(`${"word ".repeat(60)}end.`, EXTRA);
    expect(out.length).toBeLessThanOrEqual(DESCRIPTION_MAX);
    expect(out.endsWith("word…")).toBe(true);
  });

  it("is deterministic", () => {
    const d = "x ".repeat(200);
    expect(fitDescription(d, EXTRA)).toBe(fitDescription(d, EXTRA));
  });
});

describe("fitTitle", () => {
  it("keeps the brand suffix when it fits in 60 characters", () => {
    expect(fitTitle("Manufacturers")).toBe("Manufacturers");
  });

  it("drops the suffix when it would push the title past 60 characters", () => {
    const t = "Unitree Robotics G1 Basic: Specs, Status & Evidence";
    expect(fitTitle(t)).toEqual({ absolute: t });
  });
});
