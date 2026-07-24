import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import HomePage from "../app/page";

describe("HomePage (app shell)", () => {
  it("renders the HumanoidOnline heading", () => {
    render(<HomePage />);
    // getByRole throws if absent, so this asserts the shell rendered.
    const heading = screen.getByRole("heading", { name: /humanoidonline/i });
    expect(heading).toBeTruthy();
  });
});
