// The one place the console reaches the engine. Pages import `getApi` and the types from here.
import { ApiError, type EngineApi } from "./client";
import { createHttpApi } from "./http";

export { ApiError, type EngineApi } from "./client";
export type * from "./types";

/** The engine API at `ABHIYOGAH_API_URL`, called with the key in `ABHIYOGAH_API_KEY` (server side only). */
export function getApi(env: Record<string, string | undefined> = process.env): EngineApi {
  const url = env.ABHIYOGAH_API_URL;
  const key = env.ABHIYOGAH_API_KEY;
  if (!url || !key) {
    throw new ApiError(503, "Set ABHIYOGAH_API_URL and ABHIYOGAH_API_KEY to reach the engine API");
  }
  return createHttpApi(url, key);
}
