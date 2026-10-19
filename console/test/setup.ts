import { cleanup } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";
import { API_URL, replayFetch } from "./recorded";

beforeEach(() => {
  vi.stubEnv("ABHIYOGAH_API_URL", API_URL);
  vi.stubEnv("ABHIYOGAH_API_KEY", "test-key");
  vi.stubGlobal("fetch", replayFetch);
});

afterEach(() => {
  cleanup();
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});
