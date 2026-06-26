/**
 * SQLite → PostgreSQL 数据迁移脚本
 *
 * 用法：
 *   在服务器上执行：node scripts/migrate-to-pg.js /path/to/dev.db
 *
 * 前置条件：
 *   1. PostgreSQL 数据库已创建（通过 prisma db push）
 *   2. DATABASE_URL 环境变量指向 PostgreSQL
 *   3. npm install pg better-sqlite3（两个包）
 */

const Database = require("better-sqlite3");
const { Client } = require("pg");
const path = require("path");

// ============================================================
// 配置
// ============================================================

const SQLITE_DB_PATH = process.argv[2] || path.join(__dirname, "..", "prisma", "dev.db");
const PG_CONNECTION = process.env.DATABASE_URL;

if (!PG_CONNECTION) {
  console.error("❌ 请设置 DATABASE_URL 环境变量指向 PostgreSQL");
  console.error("   例如: export DATABASE_URL=your_postgresql_connection_string");
  process.exit(1);
}

console.log("📦 SQLite 文件:", SQLITE_DB_PATH);
console.log("🐘 PostgreSQL:", PG_CONNECTION.replace(/\/\/.*@/, "//***:***@"));

// ============================================================
// 工具函数：SQLite 时间戳 → PostgreSQL ISO 字符串
// ============================================================
// SQLite 可能存毫秒时间戳（如 1777279965943）或 ISO 字符串
// PostgreSQL 只接受 ISO 8601 字符串

function normalizeDate(val) {
  if (val === null || val === undefined) return null;
  // 如果已经是 ISO 格式字符串
  if (typeof val === "string" && /^\d{4}-\d{2}-\d{2}/.test(val)) return val;
  // 数字或数字字符串（毫秒时间戳）
  const num = typeof val === "string" ? Number(val) : val;
  if (typeof num === "number" && !isNaN(num) && num > 0) {
    const ts = num > 1000000000000 ? num : num * 1000;
    return new Date(ts).toISOString();
  }
  const d = new Date(val);
  if (!isNaN(d.getTime())) return d.toISOString();
  return null;
}

// 所有日期时间字段名
const DATE_COLUMNS = new Set([
  "createdAt", "updatedAt", "completedAt",
]);

// ============================================================
// 表映射（SQLite 表名 → 字段列表 + 类型转换）
// ============================================================

const TABLES = {
  // 基础表（无依赖）
  User: {
    columns: ["id", "username", "passwordHash", "createdAt", "updatedAt"],
    transform: (row) => row,
  },
  WritingStyle: {
    columns: [
      "id", "name", "sourceType", "creativeMethodology", "uniqueMarkers",
      "generationStyle", "expressionFeatures", "styleTraits", "portraitMarkdown",
      "originalCharCount", "usedCharCount", "truncated", "errorMessage",
      "createdAt", "updatedAt",
    ],
    transform: (row) => ({ ...row, truncated: row.truncated ? true : false }),
  },

  // 依赖 WritingStyle, User
  Novel: {
    columns: [
      "id", "name", "summary", "storyProgress", "appliedStyleId",
      "userId", "createdAt", "updatedAt",
    ],
    transform: (row) => row,
  },

  // 依赖 WritingStyle
  StyleReference: {
    columns: ["id", "styleId", "filename", "filepath", "charCount", "status", "errorMessage", "createdAt"],
    transform: (row) => row,
  },
  StylePortraitTask: {
    columns: ["id", "styleId", "status", "errorMessage", "createdAt", "updatedAt"],
    transform: (row) => row,
  },

  // 依赖 Novel
  Chapter: {
    columns: ["id", "novelId", "title", "content", "order", "status", "completedAt", "createdAt", "updatedAt"],
    transform: (row) => row,
  },
  StoryBackground: {
    columns: ["id", "novelId", "content", "createdAt", "updatedAt"],
    transform: (row) => row,
  },
  WorldSetting: {
    columns: ["id", "novelId", "content", "createdAt", "updatedAt"],
    transform: (row) => row,
  },
  WritingBible: {
    columns: [
      "id", "novelId", "genre", "targetReaders", "coreSellingPoint",
      "readerPromise", "appealModel", "taboo", "comparableTitles", "notes",
      "createdAt", "updatedAt",
    ],
    transform: (row) => row,
  },
  Outline: {
    columns: ["id", "novelId", "content", "createdAt", "updatedAt"],
    transform: (row) => row,
  },
  PlotProgress: {
    columns: ["id", "novelId", "currentStage", "currentGoal", "currentConflict", "nextMilestone", "updatedAt"],
    transform: (row) => row,
  },
  ReferenceMaterial: {
    columns: ["id", "novelId", "title", "type", "content", "sourceUrl", "createdAt", "updatedAt"],
    transform: (row) => row,
  },
  Foreshadowing: {
    columns: [
      "id", "novelId", "name", "plantedAt", "plantedContent",
      "expectedPayoff", "payoffAt", "status", "createdAt", "updatedAt",
    ],
    transform: (row) => row,
  },
  OutlineNode: {
    columns: [
      "id", "novelId", "parentId", "title", "content", "order",
      "status", "estimatedWordCount", "actualWordCount", "linkedChapterId",
      "createdAt", "updatedAt",
    ],
    transform: (row) => row,
  },
  WritingConfig: {
    columns: ["id", "novelId", "defaultWordCount", "enabledAgents", "createdAt", "updatedAt"],
    transform: (row) => row,
  },
  Glossary: {
    columns: ["id", "novelId", "term", "definition", "category", "createdAt", "updatedAt"],
    transform: (row) => row,
  },

  // 依赖 Novel + Faction
  Character: {
    columns: [
      "id", "novelId", "name", "aliases", "gender", "age", "appearance",
      "personality", "identity", "background", "factionId",
      "coreDesire", "behaviorBoundaries", "speechStyle", "relationshipPrinciples",
      "shortTermGoal", "powerLevel", "combatAbility", "specialSkills",
      "currentStatus", "statusNote", "createdAt", "updatedAt",
    ],
    transform: (row) => row,
  },

  // 依赖 Novel + Location
  Faction: {
    columns: ["id", "novelId", "name", "aliases", "type", "baseId", "description", "createdAt", "updatedAt"],
    transform: (row) => row,
  },

  // 依赖 Novel + Location (自引用)
  Location: {
    columns: [
      "id", "novelId", "name", "aliases", "type", "parentId",
      "climate", "culture", "description", "createdAt", "updatedAt",
    ],
    transform: (row) => row,
  },

  // 依赖 Novel + Character
  Item: {
    columns: [
      "id", "novelId", "name", "aliases", "type", "rarity",
      "effect", "origin", "description", "ownerId", "createdAt", "updatedAt",
    ],
    transform: (row) => row,
  },

  // 依赖 Chapter
  ChapterProgress: {
    columns: ["id", "chapterId", "content", "createdAt", "updatedAt"],
    transform: (row) => row,
  },
  ChapterQualityCheck: {
    columns: [
      "id", "chapterId", "type", "status", "title", "summary", "result",
      "scoreHook", "scoreTension", "scorePayoff", "scorePacing",
      "scoreEndingHook", "scoreReaderPromise", "scoreOverall",
      "qualityGate", "rewriteBrief", "createdAt", "updatedAt",
    ],
    transform: (row) => row,
  },

  // 依赖 Character
  CharacterRelation: {
    columns: [
      "id", "characterId", "targetId", "relationType", "intimacy",
      "description", "startDate", "endDate", "createdAt", "updatedAt",
    ],
    transform: (row) => row,
  },
  CharacterExperience: {
    columns: ["id", "characterId", "chapterId", "content", "order", "createdAt", "updatedAt"],
    transform: (row) => row,
  },
  CharacterStateChange: {
    columns: [
      "id", "characterId", "chapterId", "changeType", "description",
      "beforeState", "afterState", "createdAt",
    ],
    transform: (row) => row,
  },

  // 依赖 Novel + Chapter
  WritingTask: {
    columns: [
      "id", "novelId", "chapterId", "targetWordCount", "selectedAgents",
      "phase", "agentOutputs", "generatedContent", "finalContent",
      "conversationHistory", "foreshadowingUpdates", "outlineUpdates",
      "characterChanges", "createdAt", "updatedAt",
    ],
    transform: (row) => row,
  },
  WritingSession: {
    columns: ["id", "novelId", "chapterId", "title", "phase", "createdAt", "updatedAt"],
    transform: (row) => row,
  },

  // 依赖 WritingSession
  WritingMessage: {
    columns: [
      "id", "sessionId", "role", "agentId", "content",
      "intent", "metadata", "parentId", "createdAt",
    ],
    transform: (row) => row,
  },

  // 依赖 User
  TokenUsage: {
    columns: [
      "id", "userId", "model", "promptTokens", "completionTokens",
      "cachedTokens", "totalTokens", "agentId", "novelId", "createdAt",
    ],
    transform: (row) => row,
  },
};

// ============================================================
// 导入顺序（按依赖顺序排列）
// ============================================================

const IMPORT_ORDER = [
  // 第一层：无依赖
  "User",
  "WritingStyle",
  // 第二层：依赖第一层
  "StyleReference",
  "StylePortraitTask",
  "Novel",
  // 第三层：依赖 Novel
  "Chapter",
  "StoryBackground",
  "WorldSetting",
  "WritingBible",
  "Outline",
  "PlotProgress",
  "ReferenceMaterial",
  "Foreshadowing",
  "OutlineNode",
  "WritingConfig",
  "Glossary",
  "Location",
  "Faction",
  // 第四层：依赖 Novel + Character/Faction/Location
  "Character",
  "Item",
  // 第五层：依赖 Chapter
  "ChapterProgress",
  "ChapterQualityCheck",
  // 第六层：依赖 Character
  "CharacterRelation",
  "CharacterExperience",
  "CharacterStateChange",
  // 第七层：依赖 Novel + Chapter
  "WritingTask",
  "WritingSession",
  // 第八层：依赖 WritingSession
  "WritingMessage",
  // 第九层：依赖 User
  "TokenUsage",
];

// ============================================================
// FK 关系定义：{ childTable, childCol, parentTable }
// 用于插入前验证父 ID 是否存在
// ============================================================

const FK_REFS = [
  // Novel → User, WritingStyle
  { table: "Novel", col: "userId", parent: "User" },
  { table: "Novel", col: "appliedStyleId", parent: "WritingStyle" },
  // Chapter → Novel
  { table: "Chapter", col: "novelId", parent: "Novel" },
  // StoryBackground, WorldSetting, WritingBible, Outline, PlotProgress → Novel
  { table: "StoryBackground", col: "novelId", parent: "Novel" },
  { table: "WorldSetting", col: "novelId", parent: "Novel" },
  { table: "WritingBible", col: "novelId", parent: "Novel" },
  { table: "Outline", col: "novelId", parent: "Novel" },
  { table: "PlotProgress", col: "novelId", parent: "Novel" },
  { table: "ReferenceMaterial", col: "novelId", parent: "Novel" },
  { table: "Foreshadowing", col: "novelId", parent: "Novel" },
  { table: "OutlineNode", col: "novelId", parent: "Novel" },
  { table: "OutlineNode", col: "parentId", parent: "OutlineNode" },
  { table: "WritingConfig", col: "novelId", parent: "Novel" },
  { table: "Glossary", col: "novelId", parent: "Novel" },
  // Location → Novel, Location (自引用)
  { table: "Location", col: "novelId", parent: "Novel" },
  { table: "Location", col: "parentId", parent: "Location" },
  // Faction → Novel, Location
  { table: "Faction", col: "novelId", parent: "Novel" },
  { table: "Faction", col: "baseId", parent: "Location" },
  // Character → Novel, Faction
  { table: "Character", col: "novelId", parent: "Novel" },
  { table: "Character", col: "factionId", parent: "Faction" },
  // Item → Novel, Character
  { table: "Item", col: "novelId", parent: "Novel" },
  { table: "Item", col: "ownerId", parent: "Character" },
  // ChapterProgress, ChapterQualityCheck → Chapter
  { table: "ChapterProgress", col: "chapterId", parent: "Chapter" },
  { table: "ChapterQualityCheck", col: "chapterId", parent: "Chapter" },
  // CharacterRelation, CharacterExperience, CharacterStateChange → Character
  { table: "CharacterRelation", col: "characterId", parent: "Character" },
  { table: "CharacterRelation", col: "targetId", parent: "Character" },
  { table: "CharacterExperience", col: "characterId", parent: "Character" },
  { table: "CharacterStateChange", col: "characterId", parent: "Character" },
  // WritingTask, WritingSession → Novel, Chapter
  { table: "WritingTask", col: "novelId", parent: "Novel" },
  { table: "WritingTask", col: "chapterId", parent: "Chapter" },
  { table: "WritingSession", col: "novelId", parent: "Novel" },
  { table: "WritingSession", col: "chapterId", parent: "Chapter" },
  // WritingMessage → WritingSession
  { table: "WritingMessage", col: "sessionId", parent: "WritingSession" },
  // TokenUsage → User
  { table: "TokenUsage", col: "userId", parent: "User" },
  // StyleReference, StylePortraitTask → WritingStyle
  { table: "StyleReference", col: "styleId", parent: "WritingStyle" },
  { table: "StylePortraitTask", col: "styleId", parent: "WritingStyle" },
];

// ============================================================
// 主流程
// ============================================================

async function main() {
  // 1. 连接 SQLite
  console.log("\n🔌 连接 SQLite...");
  const sqlite = new Database(SQLITE_DB_PATH);
  sqlite.pragma("journal_mode = WAL");

  // 2. 连接 PostgreSQL
  console.log("🔌 连接 PostgreSQL...");
  const pg = new Client({ connectionString: PG_CONNECTION });
  await pg.connect();

  // 3. 清空旧数据（逆序）
  console.log("\n🧹 清空旧数据...");
  for (const tableName of [...IMPORT_ORDER].reverse()) {
    if (!TABLES[tableName]) continue;
    try { await pg.query(`DELETE FROM "${tableName}"`); } catch (err) { /* 忽略 */ }
  }
  console.log("   ✅ 清空完成");

  // 4. 逐表迁移，记录已插入的 ID 用于 FK 校验
  const insertedIds = {}; // { TableName: Set<id> }
  let totalRows = 0;
  let totalSkipped = 0;

  for (const tableName of IMPORT_ORDER) {
    const config = TABLES[tableName];
    if (!config) continue;

    // 检查 SQLite 中是否存在该表
    let rows;
    try {
      rows = sqlite.prepare(`SELECT * FROM "${tableName}"`).all();
    } catch (e) {
      console.log(`  ⏭️  ${tableName}: SQLite 中不存在此表，跳过`);
      insertedIds[tableName] = new Set();
      continue;
    }

    if (rows.length === 0) {
      console.log(`  📭 ${tableName}: 0 行（空表，跳过）`);
      insertedIds[tableName] = new Set();
      continue;
    }

    const columns = config.columns;
    const colNames = columns.map((c) => `"${c}"`).join(", ");
    const placeholders = columns.map((_, i) => `$${i + 1}`).join(", ");

    // 自引用表：先插 parentId IS NULL，再插有 parentId 的
    const isSelfRef = tableName === "Location" || tableName === "OutlineNode";
    let batch1 = rows;
    let batch2 = [];
    if (isSelfRef) {
      batch1 = rows.filter((r) => r.parentId === null || r.parentId === undefined);
      batch2 = rows.filter((r) => r.parentId !== null && r.parentId !== undefined);
    }

    insertedIds[tableName] = new Set();
    let inserted = 0;
    let skipped = 0;

    for (const batch of [batch1, batch2]) {
      for (const row of batch) {
        const transformed = config.transform(row);

        // FK 校验
        const fkViolation = FK_REFS
          .filter((fk) => fk.table === tableName)
          .find((fk) => {
            const fkVal = transformed[fk.col];
            if (fkVal === null || fkVal === undefined) return false; // nullable FK OK
            const parentIds = insertedIds[fk.parent];
            return parentIds && !parentIds.has(fkVal);
          });

        if (fkViolation) {
          skipped++;
          continue;
        }

        const values = columns.map((col) => {
          let val = transformed[col];
          if (DATE_COLUMNS.has(col) && val !== null && val !== undefined) {
            val = normalizeDate(val);
          }
          if (col === "truncated" && typeof val === "number") return val === 1;
          return val;
        });

        try {
          await pg.query(`INSERT INTO "${tableName}" (${colNames}) VALUES (${placeholders})`, values);
          insertedIds[tableName].add(transformed.id);
          inserted++;
        } catch (err) {
          skipped++;
        }
      }
    }

    if (skipped > 0) {
      console.log(`  ⚠️  ${tableName}: ${inserted} 行成功, ${skipped} 行跳过（FK不存在/格式错误）`);
    } else {
      console.log(`  ✅ ${tableName}: ${inserted} 行`);
    }
    totalRows += inserted;
    totalSkipped += skipped;
  }

  // 5. 关闭连接
  sqlite.close();
  await pg.end();

  if (totalSkipped > 0) {
    console.log(`\n⚠️  迁移完成：${totalRows} 行成功, ${totalSkipped} 行跳过（FK 引用不存在）`);
    console.log("  这是正常的：SQLite 中存在孤儿记录（引用了不存在的父记录）");
  } else {
    console.log(`\n🎉 迁移完成！共迁移 ${totalRows} 行数据到 PostgreSQL`);
  }
}

main().catch((err) => {
  console.error("迁移失败:", err);
  process.exit(1);
});
