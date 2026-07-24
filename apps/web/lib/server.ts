// Server-side base URL of the FastAPI backend. Server Components fetch the
// knowledge API through this. `API_BASE_URL` is the server-only variable
// (never shipped to the client); `NEXT_PUBLIC_API_BASE_URL` remains available
// for any future client-side needs. Default targets a local uvicorn. Imported
// only by server modules, so the unprefixed variable never reaches the client.
export const API_BASE_URL =
  process.env.API_BASE_URL ??
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  "http://localhost:8000";
