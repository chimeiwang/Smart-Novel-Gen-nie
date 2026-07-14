import createClient from "openapi-fetch";

import type { paths } from "./generated/schema";

export type { components, operations, paths } from "./generated/schema";
export type { SseState } from "./sse";
export { createSseRequestHeaders, createSseState, parseSseFrame } from "./sse";

export function createApiClient(baseUrl = "") {
  return createClient<paths>({ baseUrl, credentials: "include" });
}
