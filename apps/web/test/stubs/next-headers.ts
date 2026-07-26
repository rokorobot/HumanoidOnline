// Unit-test stub for next/headers: request scope does not exist under vitest, so
// headers() throws — getRequestId() catches this and falls back to a generated id.
export function headers(): never {
  throw new Error("next/headers unavailable in unit tests");
}
export function cookies(): never {
  throw new Error("next/headers unavailable in unit tests");
}
