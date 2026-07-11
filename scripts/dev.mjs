import { spawn, spawnSync } from "node:child_process";
import { existsSync, mkdirSync } from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const envFile = path.join(root, ".env.local");

if (!existsSync(envFile)) {
  console.error("缺少 .env.local，请先复制 .env.local.example 并填写本地数据库配置。");
  process.exit(1);
}

process.chdir(root);
process.loadEnvFile(envFile);

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
  if (!process.env[key]) process.env[key] = value;
}

const requiredValues = ["DATABASE_URL", "REDIS_URL", "JWT_SECRET"];
const missingValues = requiredValues.filter((key) => !process.env[key]?.trim());
if (missingValues.length > 0) {
  console.error(`.env.local 缺少配置：${missingValues.join("、")}`);
  process.exit(1);
}

const requiredFiles = [
  "CORE_SERVICE_PRIVATE_KEY_PATH",
  "AGENT_SERVICE_PUBLIC_KEY_PATH",
  "CORE_SERVICE_PUBLIC_KEY_PATH",
  "AGENT_SERVICE_PRIVATE_KEY_PATH",
];
const missingFiles = requiredFiles.filter((key) => {
  const value = process.env[key]?.trim();
  return !value || !existsSync(path.resolve(root, value));
});
if (missingFiles.length > 0) {
  console.error(`本地服务密钥缺失：${missingFiles.join("、")}`);
  console.error("请先运行：uv run python scripts/generate_service_keys.py --output-dir infra/secrets");
  process.exit(1);
}

mkdirSync(process.env.UPLOADS_ROOT, { recursive: true });
mkdirSync(process.env.WORKFLOW_HUMAN_LOG_DIR, { recursive: true });

const executable = (name) => (process.platform === "win32" ? `${name}.cmd` : name);
const services = [
  {
    name: "Next.js",
    command: executable("npm"),
    args: ["run", "dev", "--workspace", "@inkforge/web"],
  },
  {
    name: "Core API",
    command: executable("uv"),
    args: [
      "run",
      "uvicorn",
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
    command: executable("uv"),
    args: [
      "run",
      "uvicorn",
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
    if (process.platform === "win32") {
      spawnSync("taskkill", ["/pid", String(child.pid), "/T", "/F"], { stdio: "ignore" });
    } else {
      child.kill("SIGTERM");
    }
  }
  process.exitCode = exitCode;
}

for (const service of services) {
  const child = spawn(service.command, service.args, {
    cwd: root,
    env: process.env,
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

process.on("SIGINT", () => stopChildren(0));
process.on("SIGTERM", () => stopChildren(0));
