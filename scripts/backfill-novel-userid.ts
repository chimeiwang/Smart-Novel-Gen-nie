/**
 * Novel.userId 回填脚本
 *
 * 用途：修复历史数据中 Novel.userId 为 null 的记录。
 * 策略：将所有 null 记录分配给数据库中第一个 User。
 *
 * 使用方式：
 *   npx tsx prisma/backfill-novel-userid.ts
 *
 * @phase 遗留 1.1 — 历史 userId 回填
 */

import { PrismaClient } from "@prisma/client";

const prisma = new PrismaClient();

async function backfillNovelUserId() {
  console.log("=== Novel.userId 回填脚本 ===\n");

  const nullNovels = await prisma.novel.findMany({
    where: { userId: null },
    select: { id: true, name: true },
  });

  if (nullNovels.length === 0) {
    console.log("✅ 所有 Novel 已有 userId，无需回填。");
    await prisma.$disconnect();
    return;
  }

  console.log(`发现 ${nullNovels.length} 条 Novel.userId = null 的记录：`);
  for (const n of nullNovels) {
    console.log(`  - ${n.name} (id: ${n.id})`);
  }
  console.log("");

  const firstUser = await prisma.user.findFirst({
    orderBy: { createdAt: "asc" },
    select: { id: true, username: true },
  });

  if (!firstUser) {
    console.log("❌ 数据库中没有 User 记录，无法回填。请先创建用户。");
    await prisma.$disconnect();
    return;
  }

  console.log(`回填目标用户: ${firstUser.username} (id: ${firstUser.id})\n`);

  for (const novel of nullNovels) {
    await prisma.novel.update({
      where: { id: novel.id },
      data: { userId: firstUser.id },
    });
    console.log(`✅ ${novel.name} → userId: ${firstUser.id}`);
  }

  console.log(`\n✅ 回填完成。共处理 ${nullNovels.length} 条记录。`);
  await prisma.$disconnect();
}

backfillNovelUserId().catch((error) => {
  console.error("回填失败:", error);
  process.exit(1);
});
