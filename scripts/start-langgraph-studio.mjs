import { spawn } from "node:child_process";

const TRUE_VALUES = new Set(["1", "true", "yes", "on"]);

function isEnabled(value) {
  return TRUE_VALUES.has(String(value ?? "").trim().toLowerCase());
}

if (!isEnabled(process.env.LANGGRAPH_STUDIO_ENABLED)) {
  console.log(
    "LangGraph Studio 已关闭。需要调试时，请在 .env 中设置 LANGGRAPH_STUDIO_ENABLED=true 后重新运行 npm run studio:dev。"
  );
  process.exit(0);
}

const child = spawn("uv", ["run", "langgraph", "dev", ...process.argv.slice(2)], {
  stdio: "inherit",
  shell: process.platform === "win32",
  env: { ...process.env, PYTHONUTF8: "1" },
});

child.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(code ?? 0);
});

child.on("error", (error) => {
  console.error("启动 LangGraph Studio 失败:", error);
  process.exit(1);
});
