// Unit-test stub for next/headers: request scope does not exist under vitest, so
// headers() throws — getRequestId() catches this and falls back to a generated id.
export function headers(): never {
  throw new Error("next/headers unavailable in unit tests");
}

// cookies() is controllable so page-level tests can act as a given browser session.
// Tests set it with __setTestCookies; by default there are no cookies.
let testCookies: Record<string, string> = {};
export function __setTestCookies(next: Record<string, string>): void {
  testCookies = { ...next };
}
export async function cookies(): Promise<{
  get: (name: string) => { name: string; value: string } | undefined;
}> {
  return {
    get: (name) => (name in testCookies ? { name, value: testCookies[name] } : undefined),
  };
}
