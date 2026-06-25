/**
 * 数据迁移脚本：SQLite → PostgreSQL
 * 将 prisma/dev.db 中的设定数据迁移到 PostgreSQL
 *
 * 迁移的表（含依赖）：
 *   User → Novel → Location → Faction → Character → CharacterRelation → StoryBackground → WorldSetting
 *
 * 用法：node scripts/migrate-sqlite-to-pg.mjs
 */

import { DatabaseSync } from 'node:sqlite';
import { PrismaClient } from '@prisma/client';

const SQLITE_PATH = 'prisma/dev.db';
const TARGET_NOVEL_ID = 'cmnhec5rb0000tx6g0jd0myl2';

// ============ 工具函数 ============

/** timestamp(ms) → ISO 8601 */
function toISO(ms) {
  if (typeof ms === 'number') return new Date(ms).toISOString();
  if (typeof ms === 'string' && /^\d+$/.test(ms)) return new Date(parseInt(ms)).toISOString();
  return ms; // 已经是字符串格式
}

/** 移除 SQLite 特有列（如 _prisma 内部列） */
function cleanRow(row, allowedKeys) {
  const cleaned = {};
  for (const key of allowedKeys) {
    if (key in row) {
      const val = row[key];
      // 转换 DateTime 字段
      if (['createdAt', 'updatedAt', 'completedAt', 'startDate', 'endDate'].includes(key) && val != null) {
        cleaned[key] = toISO(val);
      } else {
        cleaned[key] = val;
      }
    }
  }
  return cleaned;
}

// ============ 主流程 ============

async function main() {
  console.log('🔍 打开 SQLite 数据库...');
  const sqlite = new DatabaseSync(SQLITE_PATH);

  console.log('🔌 连接 PostgreSQL...');
  const prisma = new PrismaClient();
  await prisma.$connect();
  console.log('✅ 连接成功\n');

  // ---- 1. User ----
  const sqliteUser = sqlite.prepare('SELECT * FROM User WHERE id = ?').get('cmptrmvbz0000a27fq43x0jmj');
  if (!sqliteUser) {
    console.error('❌ SQLite 中找不到 User');
    process.exit(1);
  }

  const userData = {
    id: sqliteUser.id,
    username: sqliteUser.username,
    passwordHash: sqliteUser.passwordHash,
    createdAt: toISO(sqliteUser.createdAt),
    updatedAt: toISO(sqliteUser.updatedAt),
  };

  const pgUser = await prisma.user.upsert({
    where: { id: sqliteUser.id },
    create: userData,
    update: userData,
  });
  console.log(`✅ User: ${pgUser.username} (${pgUser.id})`);

  // ---- 2. Novel ----
  const sqliteNovel = sqlite.prepare('SELECT * FROM Novel WHERE id = ?').get(TARGET_NOVEL_ID);
  if (!sqliteNovel) {
    console.error('❌ SQLite 中找不到 Novel');
    process.exit(1);
  }

  const novelData = {
    id: sqliteNovel.id,
    name: sqliteNovel.name,
    summary: sqliteNovel.summary,
    storyProgress: sqliteNovel.storyProgress,
    appliedStyleId: sqliteNovel.appliedStyleId,
    userId: sqliteNovel.userId,
    createdAt: toISO(sqliteNovel.createdAt),
    updatedAt: toISO(sqliteNovel.updatedAt),
  };

  const pgNovel = await prisma.novel.upsert({
    where: { id: TARGET_NOVEL_ID },
    create: novelData,
    update: novelData,
  });
  console.log(`✅ Novel: ${pgNovel.name} (${pgNovel.id})`);

  // ---- 3. Location ----
  const sqliteLocations = sqlite.prepare('SELECT * FROM Location WHERE novelId = ?').all(TARGET_NOVEL_ID);
  console.log(`\n📍 Location: ${sqliteLocations.length} 条`);

  const locKeys = ['id', 'novelId', 'name', 'aliases', 'type', 'parentId', 'climate', 'culture', 'description', 'createdAt', 'updatedAt'];

  for (const row of sqliteLocations) {
    const data = cleanRow(row, locKeys);
    await prisma.location.upsert({
      where: { id: data.id },
      create: data,
      update: data,
    });
    console.log(`  ✅ ${data.name} (${data.id})`);
  }

  // ---- 4. Faction ----
  const sqliteFactions = sqlite.prepare('SELECT * FROM Faction WHERE novelId = ?').all(TARGET_NOVEL_ID);
  console.log(`\n🏰 Faction: ${sqliteFactions.length} 条`);

  const factionKeys = ['id', 'novelId', 'name', 'aliases', 'type', 'baseId', 'description', 'createdAt', 'updatedAt'];

  for (const row of sqliteFactions) {
    const data = cleanRow(row, factionKeys);
    await prisma.faction.upsert({
      where: { id: data.id },
      create: data,
      update: data,
    });
    console.log(`  ✅ ${data.name} (${data.id})`);
  }

  // ---- 5. Character ----
  const sqliteCharacters = sqlite.prepare('SELECT * FROM Character WHERE novelId = ?').all(TARGET_NOVEL_ID);
  console.log(`\n👤 Character: ${sqliteCharacters.length} 条`);

  const charKeys = [
    'id', 'novelId', 'name', 'aliases', 'gender', 'age', 'appearance',
    'personality', 'identity', 'background', 'factionId',
    'powerLevel', 'combatAbility', 'specialSkills',
    'currentStatus', 'statusNote', 'createdAt', 'updatedAt',
  ];

  for (const row of sqliteCharacters) {
    const data = cleanRow(row, charKeys);
    // currentStatus 是枚举值，SQLite 存的是字符串，直接映射
    if (data.currentStatus && !['active', 'missing', 'dead', 'imprisoned', 'unknown'].includes(data.currentStatus)) {
      console.log(`  ⚠️ 未知状态 "${data.currentStatus}"，设为 active`);
      data.currentStatus = 'active';
    }
    await prisma.character.upsert({
      where: { id: data.id },
      create: data,
      update: data,
    });
    console.log(`  ✅ ${data.name} (${data.id})`);
  }

  // ---- 6. CharacterRelation ----
  const sqliteRelations = sqlite.prepare(`
    SELECT cr.* FROM CharacterRelation cr
    JOIN Character c ON cr.characterId = c.id
    WHERE c.novelId = ?
  `).all(TARGET_NOVEL_ID);
  console.log(`\n🔗 CharacterRelation: ${sqliteRelations.length} 条`);

  const relKeys = ['id', 'characterId', 'targetId', 'relationType', 'intimacy', 'description', 'startDate', 'endDate', 'createdAt', 'updatedAt'];

  // 验证关系类型枚举
  const validRelTypes = ['family', 'master_student', 'friend', 'enemy', 'ally', 'lover', 'rival', 'subordinate', 'acquaintance', 'other'];

  for (const row of sqliteRelations) {
    const data = cleanRow(row, relKeys);
    if (!validRelTypes.includes(data.relationType)) {
      console.log(`  ⚠️ 未知关系类型 "${data.relationType}"，设为 other`);
      data.relationType = 'other';
    }
    await prisma.characterRelation.upsert({
      where: { id: data.id },
      create: data,
      update: data,
    });
    console.log(`  ✅ ${data.characterId} → ${data.targetId} (${data.relationType})`);
  }

  // ---- 7. StoryBackground ----
  const sqliteSB = sqlite.prepare('SELECT * FROM StoryBackground WHERE novelId = ?').get(TARGET_NOVEL_ID);
  console.log(`\n📖 StoryBackground: ${sqliteSB ? 1 : 0} 条`);

  if (sqliteSB) {
    const sbKeys = ['id', 'novelId', 'content', 'createdAt', 'updatedAt'];
    const data = cleanRow(sqliteSB, sbKeys);
    await prisma.storyBackground.upsert({
      where: { novelId: TARGET_NOVEL_ID },
      create: data,
      update: data,
    });
    console.log(`  ✅ ${data.id}`);
  }

  // ---- 8. WorldSetting ----
  const sqliteWS = sqlite.prepare('SELECT * FROM WorldSetting WHERE novelId = ?').get(TARGET_NOVEL_ID);
  console.log(`\n🌍 WorldSetting: ${sqliteWS ? 1 : 0} 条`);

  if (sqliteWS) {
    const wsKeys = ['id', 'novelId', 'content', 'createdAt', 'updatedAt'];
    const data = cleanRow(sqliteWS, wsKeys);
    await prisma.worldSetting.upsert({
      where: { novelId: TARGET_NOVEL_ID },
      create: data,
      update: data,
    });
    console.log(`  ✅ ${data.id}`);
  }

  // ---- 验证 ----
  console.log('\n\n📊 迁移验证：');
  const counts = {
    User: await prisma.user.count(),
    Novel: await prisma.novel.count(),
    Location: await prisma.location.count(),
    Faction: await prisma.faction.count(),
    Character: await prisma.character.count(),
    CharacterRelation: await prisma.characterRelation.count(),
    StoryBackground: await prisma.storyBackground.count(),
    WorldSetting: await prisma.worldSetting.count(),
  };
  for (const [table, count] of Object.entries(counts)) {
    console.log(`  ${table}: ${count} 条`);
  }

  // 清理
  sqlite.close();
  await prisma.$disconnect();
  console.log('\n🎉 迁移完成！');
}

main().catch((e) => {
  console.error('❌ 迁移失败:', e);
  process.exit(1);
});
