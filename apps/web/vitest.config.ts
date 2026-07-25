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
    },
  },
  test: {
    environment: "jsdom",
    globals: false,
    include: ["**/*.test.{ts,tsx}"],
  },
});
