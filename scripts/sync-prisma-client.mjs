import { createRequire } from "node:module";
import { cpSync, existsSync, rmSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const workspaceRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const clientEntry = require.resolve("@prisma/client");
const clientRequire = createRequire(clientEntry);
const generatedClientDir = path.dirname(clientRequire.resolve(".prisma/client/package.json"));
const rootClientDir = path.join(workspaceRoot, "node_modules", ".prisma", "client");

function getOutlineNodeFields(clientPath) {
  const client = require(clientPath);
  const model = client.Prisma.dmmf.datamodel.models.find((item) => item.name === "OutlineNode");
  return model?.fields.map((field) => field.name) ?? [];
}

const generatedFields = getOutlineNodeFields(generatedClientDir);

if (!generatedFields.includes("kind")) {
  throw new Error("Prisma Client 生成物缺少 OutlineNode.kind，请先确认 prisma/schema.prisma 已更新。");
}

if (path.resolve(generatedClientDir) !== path.resolve(rootClientDir)) {
  rmSync(rootClientDir, { recursive: true, force: true });
  cpSync(generatedClientDir, rootClientDir, { recursive: true });
}

if (!existsSync(path.join(rootClientDir, "schema.prisma"))) {
  throw new Error("Prisma Client 根目录同步失败：缺少 schema.prisma。");
}

const rootFields = getOutlineNodeFields(rootClientDir);

if (!rootFields.includes("kind")) {
  throw new Error("Prisma Client 根目录同步失败：OutlineNode.kind 未出现在 DMMF 中。");
}

console.log(`✔ Prisma Client 已同步：${path.relative(workspaceRoot, rootClientDir)}`);
