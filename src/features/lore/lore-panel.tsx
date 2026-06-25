"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { Form, Input, Select, InputNumber, Button, Space, Divider, Popconfirm, Card, Empty, Row, Col } from "antd";

import {
  createCharacterAction,
  updateCharacterAction,
  deleteCharacterAction,
  createCharacterExperienceAction,
  updateCharacterExperienceAction,
  deleteCharacterExperienceAction,
  createCharacterRelationAction,
  updateCharacterRelationAction,
  deleteCharacterRelationAction,
  createItemAction,
  updateItemAction,
  deleteItemAction,
  createLocationAction,
  updateLocationAction,
  deleteLocationAction,
  createFactionAction,
  updateFactionAction,
  deleteFactionAction,
  createGlossaryAction,
  updateGlossaryAction,
  deleteGlossaryAction,
} from "@/app/actions";

type LoreTabKey = "characters" | "items" | "locations" | "factions" | "glossaries";

// 角色状态枚举
type CharacterStatus = "active" | "missing" | "dead" | "imprisoned" | "unknown";

// 关系类型枚举
type RelationType = "family" | "master_student" | "friend" | "enemy" | "ally" | "lover" | "rival" | "subordinate" | "acquaintance" | "other";

// 状态显示名称
const STATUS_LABELS: Record<CharacterStatus, string> = {
  active: "活跃",
  missing: "失踪",
  dead: "死亡",
  imprisoned: "被囚禁",
  unknown: "未知",
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
  characters: Array<{
    id: string;
    name: string;
    aliases: string | null;
    gender: string | null;
    age: string | null;
    appearance: string | null;
    personality: string | null;
    identity: string | null;
    background: string | null;
    coreDesire: string | null;
    behaviorBoundaries: string | null;
    speechStyle: string | null;
    relationshipPrinciples: string | null;
    shortTermGoal: string | null;
    factionId: string | null;
    faction: { id: string; name: string } | null;
    // 新增：实力相关
    powerLevel: string | null;
    combatAbility: string | null;
    specialSkills: string | null;
    // 新增：当前状态
    currentStatus: CharacterStatus;
    statusNote: string | null;
    // 角色经历
    experiences: Array<{
      id: string;
      chapterId: string | null;
      content: string;
      order: number;
    }>;
    // 角色关系
    outgoingRelations: Array<{
      id: string;
      targetId: string;
      target: { id: string; name: string };
      relationType: RelationType;
      intimacy: number;
      description: string | null;
      startDate: string | null;
      endDate: string | null;
    }>;
    incomingRelations: Array<{
      id: string;
      characterId: string;
      character: { id: string; name: string };
      relationType: RelationType;
      intimacy: number;
      description: string | null;
    }>;
  }>;
  items: Array<{
    id: string;
    name: string;
    aliases: string | null;
    type: string | null;
    rarity: string | null;
    effect: string | null;
    origin: string | null;
    description: string | null;
    ownerId: string | null;
    owner: { id: string; name: string } | null;
  }>;
  locations: Array<{
    id: string;
    name: string;
    aliases: string | null;
    type: string | null;
    parentId: string | null;
    climate: string | null;
    culture: string | null;
    description: string | null;
  }>;
  factions: Array<{
    id: string;
    name: string;
    aliases: string | null;
    type: string | null;
    baseId: string | null;
    description: string | null;
  }>;
  glossaries: Array<{
    id: string;
    term: string;
    definition: string;
    category: string | null;
  }>;
};

export function LorePanel({
  novelId,
  characters,
  items,
  locations,
  factions,
  glossaries,
}: LorePanelProps) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [activeTab, setActiveTab] = useState<LoreTabKey>("characters");
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
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
    experiences: [] as Array<{ id?: string; chapterId: string; content: string; order: number }>,
    // 角色关系
    relations: [] as Array<{
      id?: string;
      targetId: string;
      relationType: RelationType;
      intimacy: number;
      description: string;
      startDate: string;
      endDate: string;
    }>,
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
            chapterId: e.chapterId || "",
            content: e.content,
            order: e.order,
          })),
          // 角色关系
          relations: character.outgoingRelations.map((r) => ({
            id: r.id,
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

  const handleDelete = () => {
    if (!editingId) return;
    startTransition(async () => {
      if (activeTab === "characters") {
        await deleteCharacterAction({ id: editingId, novelId });
      } else if (activeTab === "items") {
        await deleteItemAction({ id: editingId, novelId });
      } else if (activeTab === "locations") {
        await deleteLocationAction({ id: editingId, novelId });
      } else if (activeTab === "factions") {
        await deleteFactionAction({ id: editingId, novelId });
      } else if (activeTab === "glossaries") {
        await deleteGlossaryAction({ id: editingId, novelId });
      }
      closeModal();
      router.refresh();
    });
  };

  const handleSubmit = () => {
    startTransition(async () => {
      if (activeTab === "characters") {
        if (editingId) {
          await updateCharacterAction({
            id: editingId,
            novelId,
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
            factionId: characterForm.factionId,
            // 新增：实力相关
            powerLevel: characterForm.powerLevel,
            combatAbility: characterForm.combatAbility,
            specialSkills: characterForm.specialSkills,
            // 新增：当前状态
            currentStatus: characterForm.currentStatus,
            statusNote: characterForm.statusNote,
          });

          // 处理经历：先删除旧的，再创建新的
          const character = characters.find((c) => c.id === editingId);
          if (character) {
            for (const exp of character.experiences) {
              await deleteCharacterExperienceAction({ id: exp.id });
            }
          }
          for (let i = 0; i < characterForm.experiences.length; i++) {
            const exp = characterForm.experiences[i];
            if (exp.content.trim()) {
              await createCharacterExperienceAction({
                characterId: editingId,
                chapterId: exp.chapterId || undefined,
                content: exp.content,
                order: i,
              });
            }
          }

          // 处理关系：先删除旧的，再创建新的
          if (character) {
            for (const rel of character.outgoingRelations) {
              await deleteCharacterRelationAction({ id: rel.id, novelId });
            }
          }
          for (const rel of characterForm.relations) {
            if (rel.targetId && rel.relationType) {
              await createCharacterRelationAction({
                characterId: editingId,
                targetId: rel.targetId,
                relationType: rel.relationType,
                description: rel.description,
                intimacy: rel.intimacy,
                startDate: rel.startDate,
                endDate: rel.endDate,
              });
            }
          }
        } else {
          const characterId = await createCharacterAction({
            novelId,
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
            factionId: characterForm.factionId,
            // 新增：实力相关
            powerLevel: characterForm.powerLevel,
            combatAbility: characterForm.combatAbility,
            specialSkills: characterForm.specialSkills,
            // 新增：当前状态
            currentStatus: characterForm.currentStatus,
            statusNote: characterForm.statusNote,
          });

          // 创建经历
          if (characterId) {
            for (let i = 0; i < characterForm.experiences.length; i++) {
              const exp = characterForm.experiences[i];
              if (exp.content.trim()) {
                await createCharacterExperienceAction({
                  characterId,
                  chapterId: exp.chapterId || undefined,
                  content: exp.content,
                  order: i,
                });
              }
            }

            // 创建关系
            for (const rel of characterForm.relations) {
              if (rel.targetId && rel.relationType) {
                await createCharacterRelationAction({
                  characterId,
                  targetId: rel.targetId,
                  relationType: rel.relationType,
                  description: rel.description,
                  intimacy: rel.intimacy,
                  startDate: rel.startDate,
                  endDate: rel.endDate,
                });
              }
            }
          }
        }
      } else if (activeTab === "items") {
        if (editingId) {
          await updateItemAction({
            id: editingId,
            novelId,
            ...itemForm,
          });
        } else {
          await createItemAction({
            novelId,
            ...itemForm,
          });
        }
      } else if (activeTab === "locations") {
        if (editingId) {
          await updateLocationAction({
            id: editingId,
            novelId,
            ...locationForm,
          });
        } else {
          await createLocationAction({
            novelId,
            ...locationForm,
          });
        }
      } else if (activeTab === "factions") {
        if (editingId) {
          await updateFactionAction({
            id: editingId,
            novelId,
            ...factionForm,
          });
        } else {
          await createFactionAction({
            novelId,
            ...factionForm,
          });
        }
      } else if (activeTab === "glossaries") {
        if (editingId) {
          await updateGlossaryAction({
            id: editingId,
            novelId,
            ...glossaryForm,
          });
        } else {
          await createGlossaryAction({
            novelId,
            ...glossaryForm,
          });
        }
      }
      closeModal();
      router.refresh();
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
    if (activeTab === "characters") {
      if (characters.length === 0) {
        return <div className="empty">当前还没有角色设定，可以新增一个。</div>;
      }
      return characters.map((character) => (
        <button
          key={character.id}
          className="list-item list-item-button"
          type="button"
          onClick={() => openEditModal(character.id)}
        >
          <div className="meta">
            <span className={`badge ${character.currentStatus !== "active" ? "badge-warning" : ""}`}>
              {STATUS_LABELS[character.currentStatus]}
            </span>
            <strong>{character.name}</strong>
            {character.powerLevel && <span className="muted">{character.powerLevel}</span>}
            {character.identity && <span className="muted">{character.identity}</span>}
            {character.faction && <span className="muted">所属：{character.faction.name}</span>}
          </div>
          <div className="meta">
            {character.personality && <span className="muted">{character.personality}</span>}
            {character.statusNote && <span className="muted-warning">{character.statusNote}</span>}
          </div>
        </button>
      ));
    }

    if (activeTab === "items") {
      if (items.length === 0) {
        return <div className="empty">当前还没有物品设定，可以新增一个。</div>;
      }
      return items.map((item) => (
        <button
          key={item.id}
          className="list-item list-item-button"
          type="button"
          onClick={() => openEditModal(item.id)}
        >
          <div className="meta">
            <span className="badge">物品</span>
            <strong>{item.name}</strong>
            {item.type && <span className="muted">{item.type}</span>}
            {item.rarity && <span className="muted">{item.rarity}</span>}
          </div>
          {item.effect && <div className="muted">{item.effect}</div>}
        </button>
      ));
    }

    if (activeTab === "locations") {
      if (locations.length === 0) {
        return <div className="empty">当前还没有地点设定，可以新增一个。</div>;
      }
      return locations.map((location) => (
        <button
          key={location.id}
          className="list-item list-item-button"
          type="button"
          onClick={() => openEditModal(location.id)}
        >
          <div className="meta">
            <span className="badge">地点</span>
            <strong>{location.name}</strong>
            {location.type && <span className="muted">{location.type}</span>}
          </div>
          {location.description && <div className="muted">{location.description}</div>}
        </button>
      ));
    }

    if (activeTab === "factions") {
      if (factions.length === 0) {
        return <div className="empty">当前还没有势力设定，可以新增一个。</div>;
      }
      return factions.map((faction) => (
        <button
          key={faction.id}
          className="list-item list-item-button"
          type="button"
          onClick={() => openEditModal(faction.id)}
        >
          <div className="meta">
            <span className="badge">势力</span>
            <strong>{faction.name}</strong>
            {faction.type && <span className="muted">{faction.type}</span>}
          </div>
        </button>
      ));
    }

    if (activeTab === "glossaries") {
      if (glossaries.length === 0) {
        return <div className="empty">当前还没有术语设定，可以新增一个。</div>;
      }
      return glossaries.map((glossary) => (
        <button
          key={glossary.id}
          className="list-item list-item-button"
          type="button"
          onClick={() => openEditModal(glossary.id)}
        >
          <div className="meta">
            <span className="badge">术语</span>
            <strong>{glossary.term}</strong>
            {glossary.category && <span className="muted">{glossary.category}</span>}
          </div>
          <div className="muted">{glossary.definition}</div>
        </button>
      ));
    }

    // 故事背景和世界设定直接编辑，不需要列表
    return null;
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
                    { targetId: "", relationType: "friend", intimacy: 50, description: "", startDate: "", endDate: "" },
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
                    { chapterId: "", content: "", order: characterForm.experiences.length },
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
    <div className="stack">
      <div>
        <h3 className="title-md">设定库</h3>
        <p className="muted">管理角色、物品、地点、势力、术语等设定</p>
      </div>
      <div className="row row-between">
        <div className="muted">当前分类 {getListCount()} 条</div>
        <button className="button secondary" type="button" onClick={openCreateModal}>
          + 新增设定
        </button>
      </div>
      <div className="tabs">
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
      </div>

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
          position: fixed;
          top: 0;
          left: 320px;
          right: 560px;
          bottom: 0;
          background: var(--bg);
          z-index: 100;
          display: flex;
          flex-direction: column;
          animation: slideIn 0.2s ease-out;
          margin-top: 72px;
          height: calc(100vh - 72px)
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
