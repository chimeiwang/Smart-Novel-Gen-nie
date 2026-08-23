import { createServer } from "node:net";

export const MINIMUM_NODE_VERSION = "20.12.0";
export const LOCAL_DEVELOPMENT_PORTS = Object.freeze({
  web: 43119,
  coreApi: 8000,
  agentService: 8001,
});

export function isSupportedNodeVersion(version = process.versions.node) {
  const current = version.split(".").map((value) => Number.parseInt(value, 10));
  const minimum = MINIMUM_NODE_VERSION.split(".").map((value) => Number.parseInt(value, 10));
  for (let index = 0; index < minimum.length; index += 1) {
    if ((current[index] ?? 0) > minimum[index]) return true;
    if ((current[index] ?? 0) < minimum[index]) return false;
  }
  return true;
}

export async function findOccupiedPorts(ports, host = "127.0.0.1") {
  const checks = await Promise.all(ports.map(async (port) => {
    const available = await new Promise((resolve, reject) => {
      const server = createServer();
      server.unref();
      server.once("error", (error) => {
        if (error && error.code === "EADDRINUSE") resolve(false);
        else reject(error);
      });
      server.listen({ host, port, exclusive: true }, () => {
        server.close(() => resolve(true));
      });
    });
    return available ? null : port;
  }));
  return checks.filter((port) => port !== null);
}
