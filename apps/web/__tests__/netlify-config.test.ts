import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

describe("Netlify configuration", () => {
  it("installs and builds the Next.js app from its package directory", () => {
    const config = readFileSync(resolve(process.cwd(), "../../netlify.toml"), "utf8");
    const packageJson = JSON.parse(
      readFileSync(resolve(process.cwd(), "package.json"), "utf8"),
    );

    expect(config).toMatch(/base\s*=\s*"apps\/web"/);
    expect(config).toMatch(/command\s*=\s*"npm run build"/);
    expect(config).toMatch(/publish\s*=\s*"\.next"/);
    expect(packageJson.dependencies.next).toBeTruthy();
  });
});
