import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  resolve: {
    // Match the tsconfig `@/*` -> `./*` alias so unit tests can import app code
    // (e.g. lib/jsonld) the same way the app does.
    alias: {
      "@": fileURLToPath(new URL(".", import.meta.url)),
      // Server-only runtime markers used by the API client's correlation seam
      // (lib/request-id.ts) have no meaning under vitest; stub them so unit tests
      // that transitively import the client (e.g. lib/seo) still load. The guard
      // remains real in the Next build.
      "server-only": fileURLToPath(
        new URL("./test/stubs/server-only.ts", import.meta.url),
      ),
      "next/headers": fileURLToPath(
        new URL("./test/stubs/next-headers.ts", import.meta.url),
      ),
    },
  },
  test: {
    environment: "jsdom",
    globals: false,
    include: ["**/*.test.{ts,tsx}"],
  },
});
