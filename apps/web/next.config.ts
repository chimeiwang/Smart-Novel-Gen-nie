import type { NextConfig } from "next";
import path from "node:path";

const workspaceRoot = path.resolve(process.cwd(), "../..");
const coreApiUrl = process.env.CORE_API_INTERNAL_URL?.replace(/\/$/, "");

const nextConfig: NextConfig = {
  output: "standalone",
  outputFileTracingRoot: workspaceRoot,
  turbopack: {
    root: workspaceRoot,
  },
  async rewrites() {
    if (process.env.NODE_ENV !== "development" || !coreApiUrl) return [];
    return [
      {
        source: "/api/:path*",
        destination: `${coreApiUrl}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
