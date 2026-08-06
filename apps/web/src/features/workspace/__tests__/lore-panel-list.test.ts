import type { components } from "@inkforge/api-client";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { buildLoreListItems } from "../../lore/lore-list-presenter";

type CharacterDto = components["schemas"]["CharacterDto"];
type ItemDto = components["schemas"]["ItemDto"];
type LocationDto = components["schemas"]["LocationDto"];
type FactionDto = components["schemas"]["FactionDto"];
type GlossaryDto = components["schemas"]["GlossaryDto"];

const createdAt = "2026-08-06T00:00:00Z";

function createCharacter(overrides: Partial<CharacterDto> = {}): CharacterDto {
  return {
    id: "character-1",
    name: "纪寻",
    aliases: null,
    gender: null,
    age: null,
    appearance: null,
    personality: "会思考但不内耗",
    identity: "玄天宗内门弟子",
    background: null,
    coreDesire: null,
    behaviorBoundaries: null,
    speechStyle: null,
    relationshipPrinciples: null,
    shortTermGoal: null,
    factionId: "faction-1",
    faction: { id: "faction-1", name: "玄天宗" },
    powerLevel: "筑基中期",
    combatAbility: null,
    specialSkills: null,
    currentStatus: "active",
    statusNote: "正在调查遗产",
    experiences: [],
    outgoingRelations: [],
    incomingRelations: [],
    createdAt,
    updatedAt: createdAt,
    ...overrides,
  };
}

function createItem(overrides: Partial<ItemDto> = {}): ItemDto {
  return {
    id: "item-1",
    name: "照影镜",
    aliases: null,
    type: "法器",
    rarity: "稀有",
    effect: "照见灵力残痕",
    origin: null,
    description: "一面旧铜镜",
    ownerId: "character-1",
    owner: { id: "character-1", name: "纪寻" },
    createdAt,
    updatedAt: createdAt,
    ...overrides,
  };
}

function createLocation(overrides: Partial<LocationDto> = {}): LocationDto {
  return {
    id: "location-2",
    name: "藏经阁",
    aliases: null,
    type: "建筑",
    parentId: "location-1",
    climate: "常年阴凉",
    culture: null,
    description: "玄天宗收藏典籍之处",
    createdAt,
    updatedAt: createdAt,
    ...overrides,
  };
}

function createFaction(overrides: Partial<FactionDto> = {}): FactionDto {
  return {
    id: "faction-1",
    name: "玄天宗",
    aliases: null,
    type: "宗门",
    baseId: "location-1",
    description: "没落中的古老宗门",
    createdAt,
    updatedAt: createdAt,
    ...overrides,
  };
}

function createGlossary(overrides: Partial<GlossaryDto> = {}): GlossaryDto {
  return {
    id: "glossary-1",
    term: "遗产猎人",
    definition: "专门发掘修士遗产的人",
    category: "职业",
    createdAt,
    updatedAt: createdAt,
    ...overrides,
  };
}

function createData() {
  return {
    characters: [createCharacter()],
    items: [createItem()],
    locations: [
      createLocation({ id: "location-1", name: "玄天宗", parentId: null }),
      createLocation(),
    ],
    factions: [createFaction()],
    glossaries: [createGlossary()],
  };
}

test("角色摘要展示身份、状态、势力、境界和性格", () => {
  const [item] = buildLoreListItems("characters", createData());

  assert.deepEqual(item, {
    id: "character-1",
    kindLabel: "角色",
    name: "纪寻",
    initial: "纪",
    secondary: "玄天宗内门弟子",
    tags: [
      { label: "活跃", tone: "status" },
      { label: "玄天宗", tone: "neutral" },
      { label: "筑基中期", tone: "neutral" },
    ],
    summary: "会思考但不内耗",
    ariaLabel: "编辑角色：纪寻",
  });
});

test("地点、势力、物品和术语只映射现有 DTO 字段", () => {
  const data = createData();

  assert.deepEqual(buildLoreListItems("locations", data)[1], {
    id: "location-2",
    kindLabel: "地点",
    name: "藏经阁",
    initial: "藏",
    secondary: "建筑",
    tags: [
      { label: "上级：玄天宗", tone: "neutral" },
      { label: "常年阴凉", tone: "neutral" },
    ],
    summary: "玄天宗收藏典籍之处",
    ariaLabel: "编辑地点：藏经阁",
  });
  assert.deepEqual(buildLoreListItems("factions", data)[0], {
    id: "faction-1",
    kindLabel: "势力",
    name: "玄天宗",
    initial: "玄",
    secondary: "宗门",
    tags: [{ label: "总部：玄天宗", tone: "neutral" }],
    summary: "没落中的古老宗门",
    ariaLabel: "编辑势力：玄天宗",
  });
  assert.deepEqual(buildLoreListItems("items", data)[0], {
    id: "item-1",
    kindLabel: "物品",
    name: "照影镜",
    initial: "照",
    secondary: "法器",
    tags: [
      { label: "稀有", tone: "neutral" },
      { label: "持有：纪寻", tone: "neutral" },
    ],
    summary: "照见灵力残痕",
    ariaLabel: "编辑物品：照影镜",
  });
  assert.deepEqual(buildLoreListItems("glossaries", data)[0], {
    id: "glossary-1",
    kindLabel: "术语",
    name: "遗产猎人",
    initial: "遗",
    secondary: "职业",
    tags: [],
    summary: "专门发掘修士遗产的人",
    ariaLabel: "编辑术语：遗产猎人",
  });
});

test("缺失字段不生成空标签，摘要按规格回退但不截断", () => {
  const longDescription = "这是一段必须完整保留并交给 CSS 处理视觉截断的物品描述。";
  const data = createData();
  data.characters = [
    createCharacter({
      identity: null,
      factionId: null,
      faction: null,
      powerLevel: " ",
      personality: null,
      statusNote: "暂时失联",
      currentStatus: "missing",
    }),
  ];
  data.items = [
    createItem({
      type: null,
      rarity: "",
      ownerId: null,
      owner: null,
      effect: null,
      description: longDescription,
    }),
  ];

  assert.deepEqual(buildLoreListItems("characters", data)[0].tags, [
    { label: "失踪", tone: "warning" },
  ]);
  assert.equal(buildLoreListItems("characters", data)[0].summary, "暂时失联");
  assert.equal(buildLoreListItems("items", data)[0].summary, longDescription);
  assert.equal(buildLoreListItems("items", data)[0].secondary, null);
  assert.deepEqual(buildLoreListItems("items", data)[0].tags, []);
});

test("设定库使用统一摘要按钮而不是冲突的通用列表类", async () => {
  const source = await readFile(new URL("../../lore/lore-panel.tsx", import.meta.url), "utf8");

  assert.match(source, /buildLoreListItems/);
  assert.match(source, /className="lore-summary-item"/);
  assert.match(source, /aria-label=\{item\.ariaLabel\}/);
  assert.match(source, /type="button"/);
  assert.match(source, /onClick=\{\(\) => openEditModal\(item\.id\)\}/);
  assert.match(source, /lore-summary-description/);
  assert.match(source, /LORE_TAB_LABELS\[activeTab\]/);
  assert.doesNotMatch(source, /className="list-item list-item-button"/);
});

test("设定库摘要样式限制长文本并按面板宽度重排", async () => {
  const css = await readFile(new URL("../../../app/globals.css", import.meta.url), "utf8");

  assert.match(css, /\.lore-panel-root\s*\{[\s\S]*?container-type:\s*inline-size/);
  assert.match(css, /\.lore-summary-item\s*\{[\s\S]*?width:\s*100%/);
  assert.match(css, /\.lore-summary-description\s*\{[\s\S]*?-webkit-line-clamp:\s*2/);
  assert.match(css, /\.lore-summary-item:focus-visible/);
  assert.match(css, /@container lore-panel \(max-width:\s*640px\)[\s\S]*?\.lore-summary-item/);
  assert.match(css, /@media \(prefers-reduced-motion:\s*reduce\)[\s\S]*?\.lore-summary-item/);
});
