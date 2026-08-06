"use client";

import type { components } from "@inkforge/api-client";
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { Form, Input, Select, InputNumber, Button, Space, Divider, Popconfirm, Card, Empty, Row, Col } from "antd";

import { browserApi } from "@/lib/api/browser";
import { createClientRequestId } from "@/lib/api/client-request-id";
import { ApiResponseError, requireApiData } from "@/lib/api/response";
import { buildLoreListItems, type LoreListKind } from "./lore-list-presenter";
import { buildChildMutationPlan, executeChildMutationPlan } from "./lore-mutation-plan";

type LoreTabKey = LoreListKind;

// 角色状态枚举
type CharacterStatus = "active" | "missing" | "dead" | "imprisoned" | "unknown";

// 关系类型枚举
type RelationType = "family" | "master_student" | "friend" | "enemy" | "ally" | "lover" | "rival" | "subordinate" | "acquaintance" | "other";

type ExperienceDraft = {
  id?: string;
  updatedAt?: string;
  clientRequestId?: string;
  chapterId: string;
  content: string;
  order: number;
};

type RelationDraft = {
  id?: string;
  updatedAt?: string;
  clientRequestId?: string;
  targetId: string;
  relationType: RelationType;
  intimacy: number;
  description: string;
  startDate: string;
  endDate: string;
};

const LORE_TAB_LABELS: Record<LoreTabKey, string> = {
  characters: "角色",
  items: "物品",
  locations: "地点",
  factions: "势力",
  glossaries: "术语",
};

// 关系类型显示名称
const RELATION_LABELS: Record<RelationType, string> = {
  family: "家族",
  master_student: "师徒",
  friend: "朋友",
  enemy: "敌对",
  ally: "盟友",
  lover: "恋人",
  rival: "竞争对手",
  subordinate: "上下级",
  acquaintance: "熟人",
  other: "其他",
};

type LorePanelProps = {
  novelId: string;
  characters: components["schemas"]["CharacterDto"][];
  items: components["schemas"]["ItemDto"][];
  locations: components["schemas"]["LocationDto"][];
  factions: components["schemas"]["FactionDto"][];
  glossaries: components["schemas"]["GlossaryDto"][];
  selectedTab?: LoreTabKey;
  showTabs?: boolean;
  onChanged?: () => void;
};

export function LorePanel({
  novelId,
  characters,
  items,
  locations,
  factions,
  glossaries,
  selectedTab,
  showTabs = true,
  onChanged,
}: LorePanelProps) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [internalActiveTab, setActiveTab] = useState<LoreTabKey>("characters");
  const activeTab = selectedTab ?? internalActiveTab;
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [entityClientRequestId, setEntityClientRequestId] = useState(createClientRequestId);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [form] = Form.useForm();

  // 角色表单状态
  const [characterForm, setCharacterForm] = useState({
    name: "",
    aliases: "",
    gender: "",
    age: "",
    appearance: "",
    personality: "",
    identity: "",
    background: "",
    coreDesire: "",
    behaviorBoundaries: "",
    speechStyle: "",
    relationshipPrinciples: "",
    shortTermGoal: "",
    factionId: "",
    // 新增：实力相关
    powerLevel: "",
    combatAbility: "",
    specialSkills: "",
    // 新增：当前状态
    currentStatus: "active" as CharacterStatus,
    statusNote: "",
    experiences: [] as ExperienceDraft[],
    // 角色关系
    relations: [] as RelationDraft[],
  });

  // 物品表单状态
  const [itemForm, setItemForm] = useState({
    name: "",
    aliases: "",
    type: "",
    rarity: "",
    effect: "",
    origin: "",
    description: "",
    ownerId: "",
  });

  // 地点表单状态
  const [locationForm, setLocationForm] = useState({
    name: "",
    aliases: "",
    type: "",
    parentId: "",
    climate: "",
    culture: "",
    description: "",
  });

  // 势力表单状态
  const [factionForm, setFactionForm] = useState({
    name: "",
    aliases: "",
    type: "",
    baseId: "",
    description: "",
  });

  // 术语表单状态
  const [glossaryForm, setGlossaryForm] = useState({
    term: "",
    definition: "",
    category: "",
  });

  const openCreateModal = () => {
    setEditingId(null);
    setEntityClientRequestId(createClientRequestId());
    setSaveError(null);
    // 重置当前 tab 的表单
    if (activeTab === "characters") {
      setCharacterForm({
        name: "",
        aliases: "",
        gender: "",
        age: "",
        appearance: "",
        personality: "",
        identity: "",
        background: "",
        coreDesire: "",
        behaviorBoundaries: "",
        speechStyle: "",
        relationshipPrinciples: "",
        shortTermGoal: "",
        factionId: "",
        // 新增：实力相关
        powerLevel: "",
        combatAbility: "",
        specialSkills: "",
        // 新增：当前状态
        currentStatus: "active",
        statusNote: "",
        experiences: [],
        relations: [],
      });
    } else if (activeTab === "items") {
      setItemForm({
        name: "",
        aliases: "",
        type: "",
        rarity: "",
        effect: "",
        origin: "",
        description: "",
        ownerId: "",
      });
    } else if (activeTab === "locations") {
      setLocationForm({
        name: "",
        aliases: "",
        type: "",
        parentId: "",
        climate: "",
        culture: "",
        description: "",
      });
    } else if (activeTab === "factions") {
      setFactionForm({
        name: "",
        aliases: "",
        type: "",
        baseId: "",
        description: "",
      });
    } else if (activeTab === "glossaries") {
      setGlossaryForm({
        term: "",
        definition: "",
        category: "",
      });
    }
    setIsModalOpen(true);
  };

  const openEditModal = (id: string) => {
    setEditingId(id);
    setSaveError(null);
    // 根据当前 tab 和 id 加载数据
    if (activeTab === "characters") {
      const character = characters.find((c) => c.id === id);
      if (character) {
        setCharacterForm({
          name: character.name,
          aliases: character.aliases || "",
          gender: character.gender || "",
          age: character.age || "",
          appearance: character.appearance || "",
          personality: character.personality || "",
          identity: character.identity || "",
          background: character.background || "",
          coreDesire: character.coreDesire || "",
          behaviorBoundaries: character.behaviorBoundaries || "",
          speechStyle: character.speechStyle || "",
          relationshipPrinciples: character.relationshipPrinciples || "",
          shortTermGoal: character.shortTermGoal || "",
          factionId: character.factionId || "",
          // 新增：实力相关
          powerLevel: character.powerLevel || "",
          combatAbility: character.combatAbility || "",
          specialSkills: character.specialSkills || "",
          // 新增：当前状态
          currentStatus: character.currentStatus,
          statusNote: character.statusNote || "",
          experiences: character.experiences.map((e) => ({
            id: e.id,
            updatedAt: e.updatedAt,
            chapterId: e.chapterId || "",
            content: e.content,
            order: e.order,
          })),
          // 角色关系
          relations: character.outgoingRelations.map((r) => ({
            id: r.id,
            updatedAt: r.updatedAt,
            targetId: r.targetId,
            relationType: r.relationType,
            intimacy: r.intimacy,
            description: r.description || "",
            startDate: r.startDate || "",
            endDate: r.endDate || "",
          })),
        });
      }
    } else if (activeTab === "items") {
      const item = items.find((i) => i.id === id);
      if (item) {
        setItemForm({
          name: item.name,
          aliases: item.aliases || "",
          type: item.type || "",
          rarity: item.rarity || "",
          effect: item.effect || "",
          origin: item.origin || "",
          description: item.description || "",
          ownerId: item.ownerId || "",
        });
      }
    } else if (activeTab === "locations") {
      const location = locations.find((l) => l.id === id);
      if (location) {
        setLocationForm({
          name: location.name,
          aliases: location.aliases || "",
          type: location.type || "",
          parentId: location.parentId || "",
          climate: location.climate || "",
          culture: location.culture || "",
          description: location.description || "",
        });
      }
    } else if (activeTab === "factions") {
      const faction = factions.find((f) => f.id === id);
      if (faction) {
        setFactionForm({
          name: faction.name,
          aliases: faction.aliases || "",
          type: faction.type || "",
          baseId: faction.baseId || "",
          description: faction.description || "",
        });
      }
    } else if (activeTab === "glossaries") {
      const glossary = glossaries.find((g) => g.id === id);
      if (glossary) {
        setGlossaryForm({
          term: glossary.term,
          definition: glossary.definition,
          category: glossary.category || "",
        });
      }
    }
    setIsModalOpen(true);
  };

  const closeModal = () => {
    if (pending) return;
    setIsModalOpen(false);
    setEditingId(null);
  };

  const currentEntity = () => {
    if (!editingId) return undefined;
    if (activeTab === "characters") return characters.find((item) => item.id === editingId);
    if (activeTab === "items") return items.find((item) => item.id === editingId);
    if (activeTab === "locations") return locations.find((item) => item.id === editingId);
    if (activeTab === "factions") return factions.find((item) => item.id === editingId);
    return glossaries.find((item) => item.id === editingId);
  };

  const finishMutation = () => {
    setIsModalOpen(false);
    setEditingId(null);
    setSaveError(null);
    onChanged?.();
    router.refresh();
  };

  const showMutationError = (error: unknown) => {
    setSaveError(
      error instanceof ApiResponseError && error.status === 409
        ? "资料已在其他位置更新，当前表单已保留，请刷新后重试。"
        : error instanceof Error ? error.message : "保存失败，请稍后重试。",
    );
  };

  const saveCharacterChildren = async (
    characterId: string,
    character: components["schemas"]["CharacterDto"] | undefined,
  ) => {
    const originalExperiences: ExperienceDraft[] = (character?.experiences ?? []).map((item) => ({
      id: item.id,
      updatedAt: item.updatedAt,
      chapterId: item.chapterId ?? "",
      content: item.content,
      order: item.order,
    }));
    const experienceDraft = characterForm.experiences
      .filter((item) => item.content.trim())
      .map((item, order) => ({ ...item, order }));
    await executeChildMutationPlan(
      buildChildMutationPlan(originalExperiences, experienceDraft),
      {
        delete: async (item) => {
          if (!item.id || !item.updatedAt) throw new Error("经历版本信息缺失");
          requireApiData(await browserApi.DELETE(
            "/api/v1/novels/{novel_id}/experiences/{experience_id}",
            {
              params: { path: { novel_id: novelId, experience_id: item.id } },
              body: { expectedUpdatedAt: item.updatedAt },
            },
          ));
        },
        update: async (item) => {
          if (!item.id || !item.updatedAt) throw new Error("经历版本信息缺失");
          requireApiData(await browserApi.PATCH(
            "/api/v1/novels/{novel_id}/experiences/{experience_id}",
            {
              params: { path: { novel_id: novelId, experience_id: item.id } },
              body: {
                chapterId: item.chapterId || null,
                content: item.content,
                order: item.order,
                expectedUpdatedAt: item.updatedAt,
              },
            },
          ));
        },
        create: async (item) => {
          if (!item.clientRequestId) throw new Error("经历创建身份缺失");
          requireApiData(await browserApi.POST(
            "/api/v1/novels/{novel_id}/characters/{character_id}/experiences",
            {
              params: { path: { novel_id: novelId, character_id: characterId } },
              body: {
                chapterId: item.chapterId || null,
                content: item.content,
                order: item.order,
                clientRequestId: item.clientRequestId,
              },
            },
          ));
        },
      },
    );

    const originalRelations: RelationDraft[] = (character?.outgoingRelations ?? []).map((item) => ({
      id: item.id,
      updatedAt: item.updatedAt,
      targetId: item.targetId,
      relationType: item.relationType,
      intimacy: item.intimacy,
      description: item.description ?? "",
      startDate: item.startDate ?? "",
      endDate: item.endDate ?? "",
    }));
    const relationDraft = characterForm.relations.filter((item) => item.targetId);
    await executeChildMutationPlan(
      buildChildMutationPlan(originalRelations, relationDraft),
      {
        delete: async (item) => {
          if (!item.id || !item.updatedAt) throw new Error("关系版本信息缺失");
          requireApiData(await browserApi.DELETE(
            "/api/v1/novels/{novel_id}/relations/{relation_id}",
            {
              params: { path: { novel_id: novelId, relation_id: item.id } },
              body: { expectedUpdatedAt: item.updatedAt },
            },
          ));
        },
        update: async (item) => {
          if (!item.id || !item.updatedAt) throw new Error("关系版本信息缺失");
          requireApiData(await browserApi.PATCH(
            "/api/v1/novels/{novel_id}/relations/{relation_id}",
            {
              params: { path: { novel_id: novelId, relation_id: item.id } },
              body: {
                relationType: item.relationType,
                intimacy: item.intimacy,
                description: item.description,
                startDate: item.startDate,
                endDate: item.endDate,
                expectedUpdatedAt: item.updatedAt,
              },
            },
          ));
        },
        create: async (item) => {
          if (!item.clientRequestId) throw new Error("关系创建身份缺失");
          requireApiData(await browserApi.POST("/api/v1/novels/{novel_id}/relations", {
            params: { path: { novel_id: novelId } },
            body: {
              characterId,
              targetId: item.targetId,
              relationType: item.relationType,
              intimacy: item.intimacy,
              description: item.description,
              startDate: item.startDate,
              endDate: item.endDate,
              clientRequestId: item.clientRequestId,
            },
          }));
        },
      },
    );
  };

  const handleDelete = () => {
    const entity = currentEntity();
    if (!editingId || !entity) return;
    startTransition(async () => {
      setSaveError(null);
      const request = { expectedUpdatedAt: entity.updatedAt };
      try {
        if (activeTab === "characters") {
          requireApiData(await browserApi.DELETE("/api/v1/novels/{novel_id}/characters/{entity_id}", {
            params: { path: { novel_id: novelId, entity_id: editingId } }, body: request,
          }));
        } else if (activeTab === "items") {
          requireApiData(await browserApi.DELETE("/api/v1/novels/{novel_id}/items/{entity_id}", {
            params: { path: { novel_id: novelId, entity_id: editingId } }, body: request,
          }));
        } else if (activeTab === "locations") {
          requireApiData(await browserApi.DELETE("/api/v1/novels/{novel_id}/locations/{entity_id}", {
            params: { path: { novel_id: novelId, entity_id: editingId } }, body: request,
          }));
        } else if (activeTab === "factions") {
          requireApiData(await browserApi.DELETE("/api/v1/novels/{novel_id}/factions/{entity_id}", {
            params: { path: { novel_id: novelId, entity_id: editingId } }, body: request,
          }));
        } else {
          requireApiData(await browserApi.DELETE("/api/v1/novels/{novel_id}/glossary/{entity_id}", {
            params: { path: { novel_id: novelId, entity_id: editingId } }, body: request,
          }));
        }
        finishMutation();
      } catch (error) {
        showMutationError(error);
      }
    });
  };

  const handleSubmit = () => {
    startTransition(async () => {
      setSaveError(null);
      try {
        if (activeTab === "characters") {
        const characterPayload = {
          name: characterForm.name,
          aliases: characterForm.aliases,
          gender: characterForm.gender,
          age: characterForm.age,
          appearance: characterForm.appearance,
          personality: characterForm.personality,
          identity: characterForm.identity,
          background: characterForm.background,
          coreDesire: characterForm.coreDesire,
          behaviorBoundaries: characterForm.behaviorBoundaries,
          speechStyle: characterForm.speechStyle,
          relationshipPrinciples: characterForm.relationshipPrinciples,
          shortTermGoal: characterForm.shortTermGoal,
          factionId: characterForm.factionId || null,
          powerLevel: characterForm.powerLevel,
          combatAbility: characterForm.combatAbility,
          specialSkills: characterForm.specialSkills,
          currentStatus: characterForm.currentStatus,
          statusNote: characterForm.statusNote,
        };
        const character = editingId
          ? characters.find((item) => item.id === editingId)
          : undefined;
        if (editingId && character) {
          requireApiData(await browserApi.PATCH(
            "/api/v1/novels/{novel_id}/characters/{entity_id}",
            {
              params: { path: { novel_id: novelId, entity_id: editingId } },
              body: { ...characterPayload, expectedUpdatedAt: character.updatedAt },
            },
          ));
          await saveCharacterChildren(editingId, character);
        } else {
          const characterId = requireApiData(await browserApi.POST(
            "/api/v1/novels/{novel_id}/characters",
            {
              params: { path: { novel_id: novelId } },
              body: { ...characterPayload, clientRequestId: entityClientRequestId },
            },
          )).id;
          await saveCharacterChildren(characterId, undefined);
        }
      } else if (activeTab === "items") {
        if (editingId) {
          const item = items.find((value) => value.id === editingId);
          if (!item) throw new Error("物品不存在");
          requireApiData(await browserApi.PATCH("/api/v1/novels/{novel_id}/items/{entity_id}", {
            params: { path: { novel_id: novelId, entity_id: editingId } }, body: { ...itemForm, expectedUpdatedAt: item.updatedAt },
          }));
        } else {
          requireApiData(await browserApi.POST("/api/v1/novels/{novel_id}/items", {
            params: { path: { novel_id: novelId } }, body: { ...itemForm, clientRequestId: entityClientRequestId },
          }));
        }
      } else if (activeTab === "locations") {
        if (editingId) {
          const location = locations.find((value) => value.id === editingId);
          if (!location) throw new Error("地点不存在");
          requireApiData(await browserApi.PATCH("/api/v1/novels/{novel_id}/locations/{entity_id}", {
            params: { path: { novel_id: novelId, entity_id: editingId } }, body: { ...locationForm, expectedUpdatedAt: location.updatedAt },
          }));
        } else {
          requireApiData(await browserApi.POST("/api/v1/novels/{novel_id}/locations", {
            params: { path: { novel_id: novelId } }, body: { ...locationForm, clientRequestId: entityClientRequestId },
          }));
        }
      } else if (activeTab === "factions") {
        if (editingId) {
          const faction = factions.find((value) => value.id === editingId);
          if (!faction) throw new Error("势力不存在");
          requireApiData(await browserApi.PATCH("/api/v1/novels/{novel_id}/factions/{entity_id}", {
            params: { path: { novel_id: novelId, entity_id: editingId } }, body: { ...factionForm, expectedUpdatedAt: faction.updatedAt },
          }));
        } else {
          requireApiData(await browserApi.POST("/api/v1/novels/{novel_id}/factions", {
            params: { path: { novel_id: novelId } }, body: { ...factionForm, clientRequestId: entityClientRequestId },
          }));
        }
      } else if (activeTab === "glossaries") {
        if (editingId) {
          const glossary = glossaries.find((value) => value.id === editingId);
          if (!glossary) throw new Error("术语不存在");
          requireApiData(await browserApi.PATCH("/api/v1/novels/{novel_id}/glossary/{entity_id}", {
            params: { path: { novel_id: novelId, entity_id: editingId } }, body: { ...glossaryForm, expectedUpdatedAt: glossary.updatedAt },
          }));
        } else {
          requireApiData(await browserApi.POST("/api/v1/novels/{novel_id}/glossary", {
            params: { path: { novel_id: novelId } }, body: { ...glossaryForm, clientRequestId: entityClientRequestId },
          }));
        }
      }
        finishMutation();
      } catch (error) {
        showMutationError(error);
      }
    });
  };

  const getListCount = () => {
    if (activeTab === "characters") return characters.length;
    if (activeTab === "items") return items.length;
    if (activeTab === "locations") return locations.length;
    if (activeTab === "factions") return factions.length;
    if (activeTab === "glossaries") return glossaries.length;
    return 0;
  };

  const renderList = () => {
    const listItems = buildLoreListItems(activeTab, {
      characters,
      items,
      locations,
      factions,
      glossaries,
    });

    if (listItems.length === 0) {
      return <div className="empty">当前还没有{LORE_TAB_LABELS[activeTab]}设定，可以新增一个。</div>;
    }

    return listItems.map((item) => (
      <button
        key={item.id}
        className="lore-summary-item"
        type="button"
        aria-label={item.ariaLabel}
        onClick={() => openEditModal(item.id)}
      >
        <span className="lore-summary-mark" aria-hidden="true">{item.initial}</span>
        <span className="lore-summary-heading">
          <strong className="lore-summary-name">{item.name}</strong>
          {item.secondary ? <span className="lore-summary-secondary">{item.secondary}</span> : null}
        </span>
        <span className="lore-summary-content">
          {item.tags.length > 0 ? (
            <span className="lore-summary-tags">
              {item.tags.map((tag, index) => (
                <span
                  className={`lore-summary-tag lore-summary-tag-${tag.tone}`}
                  key={`${tag.tone}:${tag.label}:${index}`}
                >
                  {tag.label}
                </span>
              ))}
            </span>
          ) : null}
          {item.summary ? <span className="lore-summary-description">{item.summary}</span> : null}
        </span>
        <span className="lore-summary-arrow" aria-hidden="true">›</span>
      </button>
    ));
  };

  const renderForm = () => {
    if (activeTab === "characters") {
      return (
        <Form layout="vertical" size="middle">
          {/* 基本信息 */}
          <Divider plain style={{ margin: "8px 0" }}>基本信息</Divider>
          <Row gutter={8}>
            <Col span={8}>
              <Form.Item label="姓名" required style={{ marginBottom: 8 }}>
                <Input
                  placeholder="姓名"
                  size="small"
                  value={characterForm.name}
                  onChange={(e) => setCharacterForm({ ...characterForm, name: e.target.value })}
                />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item label="别名" style={{ marginBottom: 8 }}>
                <Input
                  placeholder="别名"
                  size="small"
                  value={characterForm.aliases}
                  onChange={(e) => setCharacterForm({ ...characterForm, aliases: e.target.value })}
                />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item label="性别" style={{ marginBottom: 8 }}>
                <Select
                  placeholder="性别"
                  size="small"
                  value={characterForm.gender || undefined}
                  onChange={(value) => setCharacterForm({ ...characterForm, gender: value })}
                  allowClear
                >
                  <Select.Option value="男">男</Select.Option>
                  <Select.Option value="女">女</Select.Option>
                  <Select.Option value="未知">未知</Select.Option>
                </Select>
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={8}>
            <Col span={8}>
              <Form.Item label="年龄" style={{ marginBottom: 8 }}>
                <Input
                  placeholder="年龄"
                  size="small"
                  value={characterForm.age}
                  onChange={(e) => setCharacterForm({ ...characterForm, age: e.target.value })}
                />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item label="身份" style={{ marginBottom: 8 }}>
                <Input
                  placeholder="身份"
                  size="small"
                  value={characterForm.identity}
                  onChange={(e) => setCharacterForm({ ...characterForm, identity: e.target.value })}
                />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item label="所属势力" style={{ marginBottom: 8 }}>
                <Select
                  placeholder="所属势力"
                  size="small"
                  value={characterForm.factionId || undefined}
                  onChange={(value) => setCharacterForm({ ...characterForm, factionId: value })}
                  allowClear
                >
                  {factions.map((f) => (
                    <Select.Option key={f.id} value={f.id}>{f.name}</Select.Option>
                  ))}
                </Select>
              </Form.Item>
            </Col>
          </Row>

          {/* 实力设定 */}
          <Divider plain style={{ margin: "8px 0" }}>实力设定</Divider>
          <Row gutter={8}>
            <Col span={24}>
              <Form.Item label="实力等级" style={{ marginBottom: 8 }}>
                <Input
                  placeholder="实力等级"
                  size="small"
                  value={characterForm.powerLevel}
                  onChange={(e) => setCharacterForm({ ...characterForm, powerLevel: e.target.value })}
                />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={8}>
            <Col span={24}>
              <Form.Item label="战斗能力" style={{ marginBottom: 8 }}>
                <Input.TextArea
                  placeholder="战斗能力描述"
                  value={characterForm.combatAbility}
                  onChange={(e) => setCharacterForm({ ...characterForm, combatAbility: e.target.value })}
                  rows={4}
                />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={8}>
            <Col span={24}>
              <Form.Item label="特殊技能" style={{ marginBottom: 8 }}>
                <Input.TextArea
                  placeholder="特殊技能/能力"
                  value={characterForm.specialSkills}
                  onChange={(e) => setCharacterForm({ ...characterForm, specialSkills: e.target.value })}
                  rows={4}
                />
              </Form.Item>
            </Col>
          </Row>

          {/* 当前状态 */}
          <Divider plain style={{ margin: "8px 0" }}>当前状态</Divider>
          <Row gutter={8}>
            <Col span={8}>
              <Form.Item label="状态" style={{ marginBottom: 8 }}>
                <Select
                  size="small"
                  value={characterForm.currentStatus}
                  onChange={(value) => setCharacterForm({ ...characterForm, currentStatus: value })}
                >
                  <Select.Option value="active">活跃</Select.Option>
                  <Select.Option value="missing">失踪</Select.Option>
                  <Select.Option value="dead">死亡</Select.Option>
                  <Select.Option value="imprisoned">被囚禁</Select.Option>
                  <Select.Option value="unknown">未知</Select.Option>
                </Select>
              </Form.Item>
            </Col>
            <Col span={16}>
              <Form.Item label="状态备注" style={{ marginBottom: 8 }}>
                <Input
                  placeholder="状态备注"
                  size="small"
                  value={characterForm.statusNote}
                  onChange={(e) => setCharacterForm({ ...characterForm, statusNote: e.target.value })}
                />
              </Form.Item>
            </Col>
          </Row>

          {/* 外貌与性格 */}
          <Divider plain style={{ margin: "8px 0" }}>外貌与性格</Divider>
          <Row gutter={8}>
            <Col span={24}>
              <Form.Item label="外貌描述" style={{ marginBottom: 8 }}>
                <Input.TextArea
                  placeholder="外貌描述"
                  value={characterForm.appearance}
                  onChange={(e) => setCharacterForm({ ...characterForm, appearance: e.target.value })}
                  rows={5}
                />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={8}>
            <Col span={24}>
              <Form.Item label="性格特点" style={{ marginBottom: 8 }}>
                <Input.TextArea
                  placeholder="性格特点"
                  value={characterForm.personality}
                  onChange={(e) => setCharacterForm({ ...characterForm, personality: e.target.value })}
                  rows={5}
                />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={8}>
            <Col span={24}>
              <Form.Item label="背景故事" style={{ marginBottom: 8 }}>
                <Input.TextArea
                  placeholder="背景故事"
                  value={characterForm.background}
                  onChange={(e) => setCharacterForm({ ...characterForm, background: e.target.value })}
                  rows={5}
                />
              </Form.Item>
            </Col>
          </Row>

          {/* 角色不变量 */}
          <Divider plain style={{ margin: "8px 0" }}>角色不变量</Divider>
          <Row gutter={8}>
            <Col span={12}>
              <Form.Item label="核心欲望" style={{ marginBottom: 8 }}>
                <Input.TextArea
                  placeholder="长期驱动力，不因短期剧情轻易改变"
                  value={characterForm.coreDesire}
                  onChange={(e) => setCharacterForm({ ...characterForm, coreDesire: e.target.value })}
                  rows={3}
                />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item label="行为边界" style={{ marginBottom: 8 }}>
                <Input.TextArea
                  placeholder="不会主动做什么、底线是什么"
                  value={characterForm.behaviorBoundaries}
                  onChange={(e) => setCharacterForm({ ...characterForm, behaviorBoundaries: e.target.value })}
                  rows={3}
                />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={8}>
            <Col span={12}>
              <Form.Item label="说话习惯" style={{ marginBottom: 8 }}>
                <Input.TextArea
                  placeholder="语气、称呼、口头禅、表达偏好"
                  value={characterForm.speechStyle}
                  onChange={(e) => setCharacterForm({ ...characterForm, speechStyle: e.target.value })}
                  rows={3}
                />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item label="关系原则" style={{ marginBottom: 8 }}>
                <Input.TextArea
                  placeholder="对亲友、敌人、师徒、盟友的稳定处理原则"
                  value={characterForm.relationshipPrinciples}
                  onChange={(e) => setCharacterForm({ ...characterForm, relationshipPrinciples: e.target.value })}
                  rows={3}
                />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={8}>
            <Col span={24}>
              <Form.Item label="短期目标" style={{ marginBottom: 8 }}>
                <Input
                  placeholder="当前阶段目标，应服务长期驱动力"
                  size="small"
                  value={characterForm.shortTermGoal}
                  onChange={(e) => setCharacterForm({ ...characterForm, shortTermGoal: e.target.value })}
                />
              </Form.Item>
            </Col>
          </Row>

          {/* 角色关系 */}
          <Divider plain style={{ margin: "8px 0" }}>
            <Space>
              角色关系
              <Button type="link" size="small" onClick={() => {
                setCharacterForm({
                  ...characterForm,
                  relations: [
                    ...characterForm.relations,
                    {
                      clientRequestId: createClientRequestId(),
                      targetId: "",
                      relationType: "friend",
                      intimacy: 50,
                      description: "",
                      startDate: "",
                      endDate: "",
                    },
                  ],
                });
              }}>
                + 添加
              </Button>
            </Space>
          </Divider>
          {characterForm.relations.map((rel, index) => (
            <Card key={index} size="small" title={`关系 ${index + 1}`} extra={
              <Button type="link" danger size="small" onClick={() => {
                setCharacterForm({
                  ...characterForm,
                  relations: characterForm.relations.filter((_, i) => i !== index),
                });
              }}>
                删除
              </Button>
            } style={{ marginBottom: 8 }}>
              <Row gutter={8}>
                <Col span={8}>
                  <Form.Item label="目标角色" style={{ marginBottom: 8 }}>
                    <Select
                      placeholder="目标角色"
                      size="small"
                      value={rel.targetId || undefined}
                      disabled={Boolean(rel.id)}
                      onChange={(value) => {
                        const newRelations = [...characterForm.relations];
                        newRelations[index] = { ...newRelations[index], targetId: value };
                        setCharacterForm({ ...characterForm, relations: newRelations });
                      }}
                      allowClear
                    >
                      {characters.filter(c => c.id !== editingId).map((c) => (
                        <Select.Option key={c.id} value={c.id}>{c.name}</Select.Option>
                      ))}
                    </Select>
                  </Form.Item>
                </Col>
                <Col span={8}>
                  <Form.Item label="关系类型" style={{ marginBottom: 8 }}>
                    <Select
                      size="small"
                      value={rel.relationType}
                      onChange={(value) => {
                        const newRelations = [...characterForm.relations];
                        newRelations[index] = { ...newRelations[index], relationType: value };
                        setCharacterForm({ ...characterForm, relations: newRelations });
                      }}
                    >
                      {Object.entries(RELATION_LABELS).map(([key, label]) => (
                        <Select.Option key={key} value={key}>{label}</Select.Option>
                      ))}
                    </Select>
                  </Form.Item>
                </Col>
                <Col span={8}>
                  <Form.Item label="亲密度" style={{ marginBottom: 8 }}>
                    <InputNumber
                      min={0}
                      max={100}
                      size="small"
                      value={rel.intimacy}
                      onChange={(value) => {
                        const newRelations = [...characterForm.relations];
                        newRelations[index] = { ...newRelations[index], intimacy: value || 0 };
                        setCharacterForm({ ...characterForm, relations: newRelations });
                      }}
                      style={{ width: "100%" }}
                    />
                  </Form.Item>
                </Col>
              </Row>
              <Row gutter={8}>
                <Col span={24}>
                  <Form.Item label="关系描述" style={{ marginBottom: 8 }}>
                    <Input.TextArea
                      placeholder="关系描述"
                      value={rel.description}
                      onChange={(e) => {
                        const newRelations = [...characterForm.relations];
                        newRelations[index] = { ...newRelations[index], description: e.target.value };
                        setCharacterForm({ ...characterForm, relations: newRelations });
                      }}
                      rows={3}
                    />
                  </Form.Item>
                </Col>
              </Row>
              <Row gutter={8}>
                <Col span={12}>
                  <Form.Item label="开始时间" style={{ marginBottom: 8 }}>
                    <Input
                      placeholder="开始"
                      size="small"
                      value={rel.startDate}
                      onChange={(e) => {
                        const newRelations = [...characterForm.relations];
                        newRelations[index] = { ...newRelations[index], startDate: e.target.value };
                        setCharacterForm({ ...characterForm, relations: newRelations });
                      }}
                    />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item label="结束时间" style={{ marginBottom: 8 }}>
                    <Input
                      placeholder="结束"
                      size="small"
                      value={rel.endDate}
                      onChange={(e) => {
                        const newRelations = [...characterForm.relations];
                        newRelations[index] = { ...newRelations[index], endDate: e.target.value };
                        setCharacterForm({ ...characterForm, relations: newRelations });
                      }}
                    />
                  </Form.Item>
                </Col>
              </Row>
            </Card>
          ))}
          {characterForm.relations.length === 0 && (
            <Empty description="暂无关系记录，点击上方按钮添加" image={Empty.PRESENTED_IMAGE_SIMPLE} />
          )}

          {/* 角色经历 */}
          <Divider plain style={{ margin: "8px 0" }}>
            <Space>
              角色经历
              <Button type="link" size="small" onClick={() => {
                setCharacterForm({
                  ...characterForm,
                  experiences: [
                    ...characterForm.experiences,
                    {
                      clientRequestId: createClientRequestId(),
                      chapterId: "",
                      content: "",
                      order: characterForm.experiences.length,
                    },
                  ],
                });
              }}>
                + 添加
              </Button>
            </Space>
          </Divider>
          {characterForm.experiences.map((exp, index) => (
            <Card key={index} size="small" title={`经历 ${index + 1}`} extra={
              <Button type="link" danger size="small" onClick={() => {
                setCharacterForm({
                  ...characterForm,
                  experiences: characterForm.experiences.filter((_, i) => i !== index),
                });
              }}>
                删除
              </Button>
            } style={{ marginBottom: 8 }}>
              <Row gutter={8}>
                <Col span={24}>
                  <Form.Item label="章节ID" style={{ marginBottom: 8 }}>
                    <Input
                      placeholder="章节ID"
                      size="small"
                      value={exp.chapterId}
                      onChange={(e) => {
                        const newExperiences = [...characterForm.experiences];
                        newExperiences[index] = { ...newExperiences[index], chapterId: e.target.value };
                        setCharacterForm({ ...characterForm, experiences: newExperiences });
                      }}
                    />
                  </Form.Item>
                </Col>
              </Row>
              <Row gutter={8}>
                <Col span={24}>
                  <Form.Item label="经历内容" style={{ marginBottom: 8 }}>
                    <Input.TextArea
                      placeholder="经历内容"
                      value={exp.content}
                      onChange={(e) => {
                        const newExperiences = [...characterForm.experiences];
                        newExperiences[index] = { ...newExperiences[index], content: e.target.value };
                        setCharacterForm({ ...characterForm, experiences: newExperiences });
                      }}
                      rows={5}
                    />
                  </Form.Item>
                </Col>
              </Row>
            </Card>
          ))}
          {characterForm.experiences.length === 0 && (
            <Empty description="暂无经历记录，点击上方按钮添加" image={Empty.PRESENTED_IMAGE_SIMPLE} />
          )}
        </Form>
      );
    }

    if (activeTab === "items") {
      return (
        <Form layout="vertical" size="middle">
          <Row gutter={8}>
            <Col span={8}>
              <Form.Item label="物品名称" required style={{ marginBottom: 8 }}>
                <Input
                  placeholder="物品名称"
                  size="small"
                  value={itemForm.name}
                  onChange={(e) => setItemForm({ ...itemForm, name: e.target.value })}
                />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item label="别名" style={{ marginBottom: 8 }}>
                <Input
                  placeholder="别名"
                  size="small"
                  value={itemForm.aliases}
                  onChange={(e) => setItemForm({ ...itemForm, aliases: e.target.value })}
                />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item label="持有者" style={{ marginBottom: 8 }}>
                <Select
                  placeholder="持有者"
                  size="small"
                  value={itemForm.ownerId || undefined}
                  onChange={(value) => setItemForm({ ...itemForm, ownerId: value })}
                  allowClear
                >
                  {characters.map((c) => (
                    <Select.Option key={c.id} value={c.id}>{c.name}</Select.Option>
                  ))}
                </Select>
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={8}>
            <Col span={8}>
              <Form.Item label="类型" style={{ marginBottom: 8 }}>
                <Input
                  placeholder="类型"
                  size="small"
                  value={itemForm.type}
                  onChange={(e) => setItemForm({ ...itemForm, type: e.target.value })}
                />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item label="稀有度" style={{ marginBottom: 8 }}>
                <Input
                  placeholder="稀有度"
                  size="small"
                  value={itemForm.rarity}
                  onChange={(e) => setItemForm({ ...itemForm, rarity: e.target.value })}
                />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item label="来源" style={{ marginBottom: 8 }}>
                <Input
                  placeholder="来源"
                  size="small"
                  value={itemForm.origin}
                  onChange={(e) => setItemForm({ ...itemForm, origin: e.target.value })}
                />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={8}>
            <Col span={24}>
              <Form.Item label="效果/功能" style={{ marginBottom: 8 }}>
                <Input.TextArea
                  placeholder="效果/功能描述"
                  value={itemForm.effect}
                  onChange={(e) => setItemForm({ ...itemForm, effect: e.target.value })}
                  rows={5}
                />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={8}>
            <Col span={24}>
              <Form.Item label="详细描述" style={{ marginBottom: 8 }}>
                <Input.TextArea
                  placeholder="详细描述"
                  value={itemForm.description}
                  onChange={(e) => setItemForm({ ...itemForm, description: e.target.value })}
                  rows={5}
                />
              </Form.Item>
            </Col>
          </Row>
        </Form>
      );
    }

    if (activeTab === "locations") {
      return (
        <Form layout="vertical" size="middle">
          <Row gutter={8}>
            <Col span={8}>
              <Form.Item label="地点名称" required style={{ marginBottom: 8 }}>
                <Input
                  placeholder="地点名称"
                  size="small"
                  value={locationForm.name}
                  onChange={(e) => setLocationForm({ ...locationForm, name: e.target.value })}
                />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item label="别名" style={{ marginBottom: 8 }}>
                <Input
                  placeholder="别名"
                  size="small"
                  value={locationForm.aliases}
                  onChange={(e) => setLocationForm({ ...locationForm, aliases: e.target.value })}
                />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item label="类型" style={{ marginBottom: 8 }}>
                <Input
                  placeholder="类型"
                  size="small"
                  value={locationForm.type}
                  onChange={(e) => setLocationForm({ ...locationForm, type: e.target.value })}
                />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={8}>
            <Col span={12}>
              <Form.Item label="父级地点" style={{ marginBottom: 8 }}>
                <Select
                  placeholder="父级地点"
                  size="small"
                  value={locationForm.parentId || undefined}
                  onChange={(value) => setLocationForm({ ...locationForm, parentId: value })}
                  allowClear
                >
                  {locations.map((l) => (
                    <Select.Option key={l.id} value={l.id}>{l.name}</Select.Option>
                  ))}
                </Select>
              </Form.Item>
            </Col>
            <Col span={6}>
              <Form.Item label="气候" style={{ marginBottom: 8 }}>
                <Input
                  placeholder="气候"
                  size="small"
                  value={locationForm.climate}
                  onChange={(e) => setLocationForm({ ...locationForm, climate: e.target.value })}
                />
              </Form.Item>
            </Col>
            <Col span={6}>
              <Form.Item label="文化" style={{ marginBottom: 8 }}>
                <Input
                  placeholder="文化"
                  size="small"
                  value={locationForm.culture}
                  onChange={(e) => setLocationForm({ ...locationForm, culture: e.target.value })}
                />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={8}>
            <Col span={24}>
              <Form.Item label="详细描述" style={{ marginBottom: 8 }}>
                <Input.TextArea
                  placeholder="详细描述"
                  value={locationForm.description}
                  onChange={(e) => setLocationForm({ ...locationForm, description: e.target.value })}
                  rows={6}
                />
              </Form.Item>
            </Col>
          </Row>
        </Form>
      );
    }

    if (activeTab === "factions") {
      return (
        <Form layout="vertical" size="middle">
          <Row gutter={8}>
            <Col span={8}>
              <Form.Item label="势力名称" required style={{ marginBottom: 8 }}>
                <Input
                  placeholder="势力名称"
                  size="small"
                  value={factionForm.name}
                  onChange={(e) => setFactionForm({ ...factionForm, name: e.target.value })}
                />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item label="别名" style={{ marginBottom: 8 }}>
                <Input
                  placeholder="别名"
                  size="small"
                  value={factionForm.aliases}
                  onChange={(e) => setFactionForm({ ...factionForm, aliases: e.target.value })}
                />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item label="类型" style={{ marginBottom: 8 }}>
                <Input
                  placeholder="类型"
                  size="small"
                  value={factionForm.type}
                  onChange={(e) => setFactionForm({ ...factionForm, type: e.target.value })}
                />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={8}>
            <Col span={24}>
              <Form.Item label="总部地点" style={{ marginBottom: 8 }}>
                <Select
                  placeholder="总部地点"
                  size="small"
                  value={factionForm.baseId || undefined}
                  onChange={(value) => setFactionForm({ ...factionForm, baseId: value })}
                  allowClear
                >
                  {locations.map((l) => (
                    <Select.Option key={l.id} value={l.id}>{l.name}</Select.Option>
                  ))}
                </Select>
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={8}>
            <Col span={24}>
              <Form.Item label="详细描述" style={{ marginBottom: 8 }}>
                <Input.TextArea
                  placeholder="详细描述"
                  value={factionForm.description}
                  onChange={(e) => setFactionForm({ ...factionForm, description: e.target.value })}
                  rows={6}
                />
              </Form.Item>
            </Col>
          </Row>
        </Form>
      );
    }

    if (activeTab === "glossaries") {
      return (
        <Form layout="vertical" size="middle">
          <Row gutter={8}>
            <Col span={12}>
              <Form.Item label="术语名称" required style={{ marginBottom: 8 }}>
                <Input
                  placeholder="术语名称"
                  size="small"
                  value={glossaryForm.term}
                  onChange={(e) => setGlossaryForm({ ...glossaryForm, term: e.target.value })}
                />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item label="分类" style={{ marginBottom: 8 }}>
                <Input
                  placeholder="分类"
                  size="small"
                  value={glossaryForm.category}
                  onChange={(e) => setGlossaryForm({ ...glossaryForm, category: e.target.value })}
                />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={8}>
            <Col span={24}>
              <Form.Item label="解释" required style={{ marginBottom: 8 }}>
                <Input.TextArea
                  placeholder="解释"
                  value={glossaryForm.definition}
                  onChange={(e) => setGlossaryForm({ ...glossaryForm, definition: e.target.value })}
                  rows={6}
                />
              </Form.Item>
            </Col>
          </Row>
        </Form>
      );
    }

    return null;
  };

  return (
    <div className="stack lore-panel-root">
      <div>
        <h3 className="title-md">设定库</h3>
        <p className="muted">管理角色、物品、地点、势力、术语等设定</p>
      </div>
      <div className="row row-between">
        <div className="lore-list-heading">
          <strong>{LORE_TAB_LABELS[activeTab]}设定</strong>
          <span>共 {getListCount()} 条</span>
        </div>
        <button className="button secondary" type="button" onClick={openCreateModal}>
          + 新增{LORE_TAB_LABELS[activeTab]}
        </button>
      </div>
      {showTabs ? <div className="tabs">
        <button
          className={`tab-button ${activeTab === "characters" ? "active" : ""}`}
          type="button"
          onClick={() => setActiveTab("characters")}
        >
          角色
        </button>
        <button
          className={`tab-button ${activeTab === "items" ? "active" : ""}`}
          type="button"
          onClick={() => setActiveTab("items")}
        >
          物品
        </button>
        <button
          className={`tab-button ${activeTab === "locations" ? "active" : ""}`}
          type="button"
          onClick={() => setActiveTab("locations")}
        >
          地点
        </button>
        <button
          className={`tab-button ${activeTab === "factions" ? "active" : ""}`}
          type="button"
          onClick={() => setActiveTab("factions")}
        >
          势力
        </button>
        <button
          className={`tab-button ${activeTab === "glossaries" ? "active" : ""}`}
          type="button"
          onClick={() => setActiveTab("glossaries")}
        >
          术语
        </button>
      </div> : null}

      <div className="list">{renderList()}</div>

      {/* 全屏编辑覆盖层 */}
      {isModalOpen && (
        <div className="lore-fullscreen-overlay">
          <div className="lore-fullscreen-header">
            <h2 className="title-lg">{editingId ? "编辑设定" : "新增设定"}</h2>
            <button
              type="button"
              className="button icon-only"
              onClick={closeModal}
              title="关闭"
            >
              ✕
            </button>
          </div>
          <div className="lore-fullscreen-content">
            <div className="lore-form-scroll">
              {renderForm()}
            </div>
          </div>
          <div className="lore-fullscreen-footer">
            {saveError ? <span className="form-error" role="alert">{saveError}</span> : null}
            <Space>
              {editingId && (
                <Popconfirm
                  title="确认删除"
                  description="确定要删除这个设定吗？此操作不可撤销。"
                  onConfirm={handleDelete}
                  okText="删除"
                  cancelText="取消"
                  okButtonProps={{ danger: true }}
                >
                  <Button danger type="primary" ghost>
                    删除
                  </Button>
                </Popconfirm>
              )}
            </Space>
            <Space>
              <Button onClick={closeModal}>取消</Button>
              <Button type="primary" onClick={handleSubmit} loading={pending}>
                {editingId ? "保存修改" : "新增设定"}
              </Button>
            </Space>
          </div>
        </div>
      )}

      <style jsx>{`
        .lore-fullscreen-overlay {
          position: absolute;
          inset: 0;
          background: var(--bg);
          z-index: 100;
          display: flex;
          flex-direction: column;
          animation: slideIn 0.2s ease-out;
          min-height: 0;
        }
        @keyframes slideIn {
          from {
            opacity: 0;
            transform: translateX(20px);
          }
          to {
            opacity: 1;
            transform: translateX(0);
          }
        }
        .lore-fullscreen-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 16px 24px;
          border-bottom: 1px solid var(--border);
          background: var(--bg);
        }
        .lore-fullscreen-content {
          flex: 1;
          overflow: hidden;
          padding: 16px 24px;
        }
        .lore-fullscreen-footer {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 12px 24px;
          border-top: 1px solid var(--border);
          background: var(--bg);
        }
      `}</style>
    </div>
  );
}
