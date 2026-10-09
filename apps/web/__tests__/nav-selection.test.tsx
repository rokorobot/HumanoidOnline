/**
 * UX-01 / P0-D - the header nav keeps the compare selection across the
 * Robots <-> Compare hop WITHOUT emitting selection-carrying anchors in HTML
 * (crawl containment): hrefs stay plain; the click reads the current URL.
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

import { DarkNav, SiteNav } from "@/components/SiteNav";
import { MobileMenu } from "@/components/MobileMenu";
import { NavLink } from "@/components/NavLink";
import { resolveNavTarget } from "@/lib/nav-selection";

function at(path: string) {
  window.history.pushState({}, "", path);
}

beforeEach(() => push.mockClear());
afterEach(() => {
  cleanup();
  at("/");
});

describe("resolveNavTarget", () => {
  it("catalogue selection -> Compare opens the comparison with those ids (any count >= 1)", () => {
    expect(resolveNavTarget("/compare", "/robots", "?compare=a,b&sort=name")).toBe("/compare?ids=a,b");
    expect(resolveNavTarget("/compare", "/robots", "?compare=a")).toBe("/compare?ids=a");
  });
  it("comparison -> Robots returns to the catalogue with the selection", () => {
    expect(resolveNavTarget("/robots", "/compare", "?ids=a,b&units=imperial")).toBe("/robots?compare=a,b");
  });
  it("Robots on the catalogue keeps its tray; Compare on /compare stays put", () => {
    expect(resolveNavTarget("/robots", "/robots", "?compare=a,b")).toBe("/robots?compare=a,b");
    expect(resolveNavTarget("/compare", "/compare", "?ids=a,b&ref=a")).toBe("/compare?ids=a,b&ref=a");
  });
  it("no selection -> null (plain navigation; /compare stays an intentional empty state)", () => {
    expect(resolveNavTarget("/compare", "/robots", "")).toBeNull();
    expect(resolveNavTarget("/compare", "/", "")).toBeNull();
    expect(resolveNavTarget("/robots", "/compare", "")).toBeNull();
    expect(resolveNavTarget("/compare", "/robots", "?compare=")).toBeNull();
    expect(resolveNavTarget("/about", "/robots", "?compare=a,b")).toBeNull();
  });
});

describe("NavLink", () => {
  it("renders a plain href and carries the selection only on click", () => {
    at("/robots?compare=4ne1-mini,agibot-a2-ultra");
    render(<NavLink href="/compare">Compare</NavLink>);
    const a = screen.getByRole("link", { name: "Compare" });
    expect(a.getAttribute("href")).toBe("/compare");
    expect(push).not.toHaveBeenCalled();
    fireEvent.click(a);
    expect(push).toHaveBeenCalledWith("/compare?ids=4ne1-mini,agibot-a2-ultra");
  });
  it("falls through to the normal link when there is no selection", () => {
    at("/about");
    render(<NavLink href="/compare">Compare</NavLink>);
    fireEvent.click(screen.getByRole("link", { name: "Compare" }));
    expect(push).not.toHaveBeenCalled();
  });
  it("Robots from a comparison returns the selection", () => {
    at("/compare?ids=a,b");
    render(<NavLink href="/robots">Robots</NavLink>);
    fireEvent.click(screen.getByRole("link", { name: "Robots" }));
    expect(push).toHaveBeenCalledWith("/robots?compare=a,b");
  });
  it("modified clicks are left to the browser", () => {
    at("/robots?compare=a,b");
    render(<NavLink href="/compare">Compare</NavLink>);
    fireEvent.click(screen.getByRole("link", { name: "Compare" }), { ctrlKey: true });
    expect(push).not.toHaveBeenCalled();
  });
});

describe("server HTML stays crawl-safe", () => {
  it("SiteNav and DarkNav emit only plain /compare and /robots hrefs", () => {
    const html = renderToStaticMarkup(
      <>
        <SiteNav active="robots" />
        <DarkNav active={null} />
      </>,
    );
    expect(html).toContain('href="/compare"');
    expect(html).toContain('href="/robots"');
    expect(html).not.toMatch(/href="[^"]*(compare=|ids=)/);
  });
});

describe("MobileMenu", () => {
  const links = [
    { key: "robots", href: "/robots", label: "Robots" },
    { key: "compare", href: "/compare", label: "Compare" },
  ];
  it("is a labelled disclosure button; opens a nav; Escape closes and refocuses", () => {
    render(<MobileMenu links={links} register="light" />);
    const btn = screen.getByRole("button", { name: "Menu" });
    expect(btn.getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByRole("navigation", { name: "Menu" })).toBeNull();
    fireEvent.click(btn);
    expect(btn.getAttribute("aria-expanded")).toBe("true");
    const nav = screen.getByRole("navigation", { name: "Menu" });
    expect(nav.id).toBe(btn.getAttribute("aria-controls"));
    expect(nav.querySelectorAll("a").length).toBe(2);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(btn.getAttribute("aria-expanded")).toBe("false");
    expect(document.activeElement).toBe(btn);
  });
  it("its Compare link also carries the selection and closes the menu", () => {
    at("/robots?compare=a,b");
    render(<MobileMenu links={links} register="dark" />);
    const btn = screen.getByRole("button", { name: "Menu" });
    fireEvent.click(btn);
    fireEvent.click(screen.getByRole("link", { name: "Compare" }));
    expect(push).toHaveBeenCalledWith("/compare?ids=a,b");
    expect(btn.getAttribute("aria-expanded")).toBe("false");
  });
});
