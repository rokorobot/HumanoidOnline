// Global vitest setup. The header nav links (components/NavLink.tsx) call
// next/navigation's useRouter, which throws outside a mounted App Router - and
// many page-level tests render SiteNav/DarkNav as plain React. Provide an inert
// default router; a test that cares (e.g. nav-selection) overrides this with its
// own vi.mock("next/navigation", ...).
import { vi } from "vitest";

vi.mock("next/navigation", async (importOriginal) => {
  const actual = await importOriginal<typeof import("next/navigation")>();
  return {
    ...actual,
    useRouter: () => ({
      push: vi.fn(),
      replace: vi.fn(),
      prefetch: vi.fn(),
      back: vi.fn(),
      forward: vi.fn(),
      refresh: vi.fn(),
    }),
  };
});
