import { ApiError, type EngineApi } from "./client";
import type { paths } from "./generated/schema";

type Ok<P extends keyof paths> = paths[P]["get"] extends {
  responses: { 200: { content: { "application/json": infer T } } };
}
  ? T
  : never;

/** An `EngineApi` that calls the engine API at `baseUrl`, authenticating with `apiKey` (`X-API-Key`). */
export function createHttpApi(baseUrl: string, apiKey: string, fetchImpl: typeof fetch = fetch): EngineApi {
  const get = async <P extends keyof paths>(path: string, query: Record<string, string | undefined> = {}) => {
    const url = new URL(path.replace(/^\//, ""), baseUrl.endsWith("/") ? baseUrl : `${baseUrl}/`);
    for (const [k, v] of Object.entries(query)) if (v !== undefined) url.searchParams.set(k, v);
    const res = await fetchImpl(url, { headers: { accept: "application/json", "x-api-key": apiKey }, cache: "no-store" });
    if (!res.ok) {
      const body = (await res.json().catch(() => null)) as { detail?: unknown } | null;
      const detail = typeof body?.detail === "string" ? `: ${body.detail}` : "";
      throw new ApiError(res.status, `${res.status} from GET ${url.pathname}${detail}`);
    }
    return (await res.json()) as Ok<P>;
  };
  const seg = encodeURIComponent;
  return {
    listComplaints: (asOf) => get<"/complaints">("/complaints", { as_of: asOf }),
    getComplaint: (id, asOf) =>
      get<"/complaints/{complaint_id}">(`/complaints/${seg(id)}`, { as_of: asOf }),
    getDecision: (id, obligationId, asOf) =>
      get<"/complaints/{complaint_id}/decisions/{obligation_id}">(
        `/complaints/${seg(id)}/decisions/${seg(obligationId)}`,
        { as_of: asOf },
      ),
    listObligations: () => get<"/obligations">("/obligations"),
  };
}
