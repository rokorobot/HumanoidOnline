// Base URL of the FastAPI backend. Foundation helper for later workstreams;
// no data fetching is wired up in WS1.
export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
