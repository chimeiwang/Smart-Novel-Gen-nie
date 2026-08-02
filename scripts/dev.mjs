import { spawn, spawnSync } from "node:child_process";
import { existsSync, mkdirSync } from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

import { ensureLocalData } from "./ensure-local-data.mjs";
import { loadLocalDataEnv, repositoryRoot } from "./local-data-env.mjs";

export async function runDevelopment({
  root = repositoryRoot,
  parentEnv = process.env,
  loadEnv = loadLocalDataEnv,
  ensureData = ensureLocalData,
  fileExists = existsSync,
  makeDirectory = mkdirSync,
  spawnProcess = spawn,
  spawnSyncProcess = spawnSync,
  processObject = process,
} = {}) {
  const childEnv = loadEnv({ root, parentEnv });
  const defaults = {
    ENVIRONMENT: "dev",
    MODEL_PROVIDER: "fake",
    CORE_API_INTERNAL_URL: "http://127.0.0.1:8000",
    AGENT_SERVICE_URL: "http://127.0.0.1:8001",
    CORE_API_URL: "http://127.0.0.1:8000",
    TRUSTED_PROXY_CIDRS: "127.0.0.1/32,::1/128",
    AGENT_SERVICE_CIDRS: "127.0.0.1/32,::1/128",
    TRUSTED_CORE_CIDRS: "127.0.0.1/32,::1/128",
    UPLOADS_ROOT: path.join(root, "uploads"),
    WORKFLOW_HUMAN_LOG_DIR: path.join(root, "logs", "workflow-events"),
  };
  for (const [key, value] of Object.entries(defaults)) {
    if (!childEnv[key]) childEnv[key] = value;
  }

  const requiredValues = ["DATABASE_URL", "REDIS_URL", "JWT_SECRET"];
  const missingValues = requiredValues.filter((key) => !childEnv[key]?.trim());
  if (missingValues.length > 0) {
    throw new Error(`.env.local 缺少配置：${missingValues.join("、")}`);
  }

  const requiredFiles = [
    "CORE_SERVICE_PRIVATE_KEY_PATH",
    "AGENT_SERVICE_PUBLIC_KEY_PATH",
    "CORE_SERVICE_PUBLIC_KEY_PATH",
    "AGENT_SERVICE_PRIVATE_KEY_PATH",
  ];
  const missingFiles = requiredFiles.filter((key) => {
    const value = childEnv[key]?.trim();
    return !value || !fileExists(path.resolve(root, value));
  });
  if (missingFiles.length > 0) {
    throw new Error(
      `本地服务密钥缺失：${missingFiles.join("、")}。请先运行 uv run python scripts/generate_service_keys.py --output-dir infra/secrets`,
    );
  }

  makeDirectory(childEnv.UPLOADS_ROOT, { recursive: true });
  makeDirectory(childEnv.WORKFLOW_HUMAN_LOG_DIR, { recursive: true });

  const npmExecPath = childEnv.npm_execpath;
  const uvicornExecutable =
    processObject.platform === "win32"
      ? path.join(root, ".venv", "Scripts", "uvicorn.exe")
      : path.join(root, ".venv", "bin", "uvicorn");
  if (!npmExecPath || !fileExists(npmExecPath)) {
    throw new Error("无法定位 npm 启动入口，请通过 npm run dev 启动项目。");
  }
  if (!fileExists(uvicornExecutable)) {
    throw new Error("缺少项目虚拟环境，请先运行：uv sync --frozen --all-packages --group dev");
  }

  await ensureData(childEnv);

  const services = [
    {
      name: "Next.js",
      command: processObject.execPath,
      args: [npmExecPath, "run", "dev", "--workspace", "@inkforge/web"],
    },
    {
      name: "Core API",
      command: uvicornExecutable,
      args: [
        "inkforge_core.app:create_app",
        "--factory",
        "--host",
        "127.0.0.1",
        "--port",
        "8000",
        "--reload",
      ],
    },
    {
      name: "Agent Service",
      command: uvicornExecutable,
      args: [
        "inkforge_agents.app:create_app",
        "--factory",
        "--host",
        "127.0.0.1",
        "--port",
        "8001",
        "--reload",
      ],
    },
  ];

  const children = [];
  let stopping = false;
  function stopChildren(exitCode) {
    if (stopping) return;
    stopping = true;
    for (const child of children) {
      if (child.exitCode !== null) continue;
      if (processObject.platform === "win32") {
        spawnSyncProcess("taskkill", ["/pid", String(child.pid), "/T", "/F"], {
          stdio: "ignore",
        });
      } else {
        child.kill("SIGTERM");
      }
    }
    processObject.exitCode = exitCode;
  }

  for (const service of services) {
    const child = spawnProcess(service.command, service.args, {
      cwd: root,
      env: childEnv,
      stdio: "inherit",
    });
    children.push(child);
    child.on("error", (error) => {
      console.error(`${service.name} 启动失败：${error.message}`);
      stopChildren(1);
    });
    child.on("exit", (code) => {
      if (!stopping) {
        console.error(`${service.name} 已退出，状态码：${code ?? "未知"}`);
        stopChildren(code === 0 ? 0 : 1);
      }
    });
  }

  processObject.on("SIGINT", () => stopChildren(0));
  processObject.on("SIGTERM", () => stopChildren(0));
  return { children, stopChildren };
}

const entry = process.argv[1] ? path.resolve(process.argv[1]) : "";
if (entry === fileURLToPath(import.meta.url)) {
  runDevelopment().catch((error) => {
    console.error(error.message);
    process.exitCode = 1;
  });
}
