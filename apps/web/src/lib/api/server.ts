import createClient from "openapi-fetch";
import { cookies, headers } from "next/headers";

import type { paths } from "@inkforge/api-client";

export async function createServerApiClient() {
  const [cookieStore, requestHeaders] = await Promise.all([cookies(), headers()]);
  const requestId = requestHeaders.get("X-Request-ID");
  const forwardedHeaders: Record<string, string> = {
    Cookie: cookieStore.toString(),
  };
  if (requestId) forwardedHeaders["X-Request-ID"] = requestId;
  return createClient<paths>({
    baseUrl: process.env.CORE_API_INTERNAL_URL ?? "http://core-api:8000",
    headers: forwardedHeaders,
  });
}
