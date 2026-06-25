"use client";

import { useMemo, useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import {
  createOutlineNodeAction,
  deleteOutlineNodeAction,
  updateOutlineAction,
  updateOutlineNodeAction,
} from "@/app/actions";

type OutlineNodeKind = "stage" | "plot_unit" | "chapter_group";
type OutlineNodeStatus = "planned" | "in_progress" | "completed" | "skipped";

type OutlineNodeDto = {
  id: string;
  title: string;
  content: string | null;
  kind: OutlineNodeKind;
  status: OutlineNodeStatus;
  order: number;
  parentId: string | null;
  estimatedWordCount: number | null;
  actualWordCount: number | null;
};

type OutlinePanelProps = {
  novelId: string;
  outline: {
    content: string;
  } | null;
  outlineNodes?: OutlineNodeDto[];
};

type NodeFormState = {
  id: string | null;
  title: string;
  content: string;
  kind: OutlineNodeKind;
  parentId: string;
  status: OutlineNodeStatus;
  estimatedWordCount: string;
  actualWordCount: string;
};

const KIND_LABELS: Record<OutlineNodeKind, string> = {
  stage: "阶段/卷",
  plot_unit: "剧情单元",
  chapter_group: "章节组",
};

const STATUS_LABELS: Record<OutlineNodeStatus, string> = {
  planned: "计划中",
  in_progress: "正在写",
  completed: "已完成",
  skipped: "已跳过",
};

const EMPTY_FORM: NodeFormState = {
  id: null,
  title: "",
  content: "",
  kind: "stage",
  parentId: "",
  status: "planned",
  estimatedWordCount: "",
  actualWordCount: "",
};

function toNumberOrNull(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const numeric = Number(trimmed);
  return Number.isFinite(numeric) ? numeric : null;
}

function getParentKind(kind: OutlineNodeKind): OutlineNodeKind | null {
  if (kind === "plot_unit") return "stage";
  if (kind === "chapter_group") return "plot_unit";
  return null;
}

function byOrderThenTitle(a: OutlineNodeDto, b: OutlineNodeDto) {
  return a.order === b.order ? a.title.localeCompare(b.title, "zh-Hans-CN") : a.order - b.order;
}

function nodeToForm(node: OutlineNodeDto): NodeFormState {
  return {
    id: node.id,
    title: node.title,
    content: node.content ?? "",
    kind: node.kind,
    parentId: node.parentId ?? "",
    status: node.status,
    estimatedWordCount: node.estimatedWordCount?.toString() ?? "",
    actualWordCount: node.actualWordCount?.toString() ?? "",
  };
}

export function OutlinePanel({ novelId, outline, outlineNodes = [] }: OutlinePanelProps) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [content, setContent] = useState(outline?.content ?? "");
  const [form, setForm] = useState<NodeFormState>(EMPTY_FORM);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const nodesByParent = useMemo(() => {
    const map = new Map<string, OutlineNodeDto[]>();
    for (const node of outlineNodes) {
      const key = node.parentId ?? "root";
      const nodes = map.get(key) ?? [];
      nodes.push(node);
      map.set(key, nodes);
    }
    for (const nodes of map.values()) nodes.sort(byOrderThenTitle);
    return map;
  }, [outlineNodes]);

  const legalParents = useMemo(() => {
    const parentKind = getParentKind(form.kind);
    if (!parentKind) return [];
    return outlineNodes
      .filter((node) => node.kind === parentKind && node.id !== form.id)
      .sort(byOrderThenTitle);
  }, [form.id, form.kind, outlineNodes]);

  const selectedNode = selectedNodeId ? outlineNodes.find((node) => node.id === selectedNodeId) ?? null : null;

  const setField = <K extends keyof NodeFormState>(key: K, value: NodeFormState[K]) => {
    setForm((current) => {
      const next = { ...current, [key]: value };
      if (key === "kind") {
        next.parentId = "";
      }
      return next;
    });
  };

  const handleSelectNode = (node: OutlineNodeDto) => {
    setSelectedNodeId(node.id);
    setForm(nodeToForm(node));
    setMessage(null);
    setError(null);
  };

  const handleNewNode = (kind: OutlineNodeKind) => {
    setSelectedNodeId(null);
    setForm({ ...EMPTY_FORM, kind });
    setMessage(null);
    setError(null);
  };

  const runAction = (action: () => Promise<void>, successMessage: string) => {
    setError(null);
    setMessage(null);
    startTransition(async () => {
      try {
        await action();
        setMessage(successMessage);
        router.refresh();
      } catch (err) {
        setError(err instanceof Error ? err.message : "操作失败");
      }
    });
  };

  const handleSaveOutline = () => {
    runAction(
      () => updateOutlineAction({ novelId, content }),
      "总纲已保存",
    );
  };

  const handleSaveNode = () => {
    const title = form.title.trim();
    if (!title) {
      setError("节点标题不能为空");
      return;
    }
    if (form.kind !== "stage" && !form.parentId) {
      setError(form.kind === "plot_unit" ? "剧情单元必须选择阶段/卷" : "章节组必须选择剧情单元");
      return;
    }

    const payload = {
      novelId,
      title,
      content: form.content,
      kind: form.kind,
      parentId: form.kind === "stage" ? null : form.parentId,
      status: form.status,
      estimatedWordCount: toNumberOrNull(form.estimatedWordCount),
      actualWordCount: toNumberOrNull(form.actualWordCount),
    };

    const nodeId = form.id;
    if (nodeId) {
      runAction(
        () => updateOutlineNodeAction({ ...payload, id: nodeId }),
        "大纲节点已更新",
      );
    } else {
      runAction(
        () => createOutlineNodeAction(payload),
        "大纲节点已创建",
      );
    }
  };

  const handleDeleteNode = () => {
    if (!form.id) return;
    const title = form.title || "当前节点";
    if (!window.confirm(`确认删除「${title}」？有子节点时系统会拒绝删除。`)) return;
    runAction(
      async () => {
        await deleteOutlineNodeAction({ novelId, id: form.id as string });
        setSelectedNodeId(null);
        setForm(EMPTY_FORM);
      },
      "大纲节点已删除",
    );
  };

  const renderTree = (parentId: string | null, depth = 0): React.ReactNode => {
    const children = nodesByParent.get(parentId ?? "root") ?? [];
    if (children.length === 0 && depth === 0) {
      return <div className="empty">还没有结构化大纲节点，可以先新增一个阶段/卷。</div>;
    }
    return children.map((node) => (
      <div className="outline-node-group" key={node.id}>
        <button
          type="button"
          className={`outline-node-item ${selectedNodeId === node.id ? "active" : ""}`}
          style={{ paddingLeft: 10 + depth * 16 }}
          onClick={() => handleSelectNode(node)}
        >
          <span className={`outline-kind-dot outline-kind-${node.kind}`} />
          <span className="outline-node-main">
            <span className="outline-node-title">{node.title}</span>
            <span className="outline-node-meta">
              {KIND_LABELS[node.kind]} · {STATUS_LABELS[node.status]}
            </span>
          </span>
        </button>
        {renderTree(node.id, depth + 1)}
      </div>
    ));
  };

  return (
    <div className="panel outline-panel">
      <div className="panel-header">
        <div>
          <h3 className="title-md">大纲</h3>
          <p className="muted">查看结构，少量修正。大纲生成和重构优先在聊天中完成。</p>
        </div>
      </div>
      <div className="panel-body stack">
        <section className="outline-summary-section">
          <div className="row row-between">
            <div>
              <h4 className="title-sm">总纲</h4>
              <p className="muted">全书方向和主线承诺。</p>
            </div>
            <button className="button secondary" type="button" onClick={handleSaveOutline} disabled={pending}>
              {pending ? "保存中..." : "保存总纲"}
            </button>
          </div>
          <textarea
            className="textarea"
            value={content}
            onChange={(event) => setContent(event.target.value)}
            placeholder="例：主角从第一卷离开故乡，逐步揭开旧时代禁术真相，最终推翻旧秩序..."
            rows={6}
          />
        </section>

        <section className="outline-structure">
          <div className="outline-tree-pane">
            <div className="row row-between outline-pane-header">
              <div>
                <h4 className="title-sm">节点树</h4>
                <p className="muted">阶段/卷 → 剧情单元 → 章节组。</p>
              </div>
            </div>
            <div className="outline-create-row">
              <button className="button ghost" type="button" onClick={() => handleNewNode("stage")}>新阶段</button>
              <button className="button ghost" type="button" onClick={() => handleNewNode("plot_unit")}>新单元</button>
              <button className="button ghost" type="button" onClick={() => handleNewNode("chapter_group")}>新章节组</button>
            </div>
            <div className="outline-tree">{renderTree(null)}</div>
          </div>

          <div className="outline-detail-pane">
            <div className="row row-between outline-pane-header">
              <div>
                <h4 className="title-sm">{selectedNode ? "编辑节点" : "新增节点"}</h4>
                <p className="muted">修改标题、层级、状态和节点内容。</p>
              </div>
              {form.id ? (
                <button className="button ghost danger" type="button" onClick={handleDeleteNode} disabled={pending}>
                  删除
                </button>
              ) : null}
            </div>

            <div className="outline-form-grid">
              <label className="stack stack-tight">
                <span className="label">标题</span>
                <input
                  className="input"
                  value={form.title}
                  onChange={(event) => setField("title", event.target.value)}
                  placeholder="例如：第一卷 离开青石镇"
                />
              </label>

              <label className="stack stack-tight">
                <span className="label">类型</span>
                <select
                  className="select"
                  value={form.kind}
                  onChange={(event) => setField("kind", event.target.value as OutlineNodeKind)}
                >
                  {Object.entries(KIND_LABELS).map(([value, label]) => (
                    <option key={value} value={value}>{label}</option>
                  ))}
                </select>
              </label>

              <label className="stack stack-tight">
                <span className="label">父节点</span>
                <select
                  className="select"
                  value={form.parentId}
                  onChange={(event) => setField("parentId", event.target.value)}
                  disabled={form.kind === "stage"}
                >
                  <option value="">{form.kind === "stage" ? "顶层节点" : "请选择父节点"}</option>
                  {legalParents.map((node) => (
                    <option key={node.id} value={node.id}>{node.title}</option>
                  ))}
                </select>
              </label>

              <label className="stack stack-tight">
                <span className="label">状态</span>
                <select
                  className="select"
                  value={form.status}
                  onChange={(event) => setField("status", event.target.value as OutlineNodeStatus)}
                >
                  {Object.entries(STATUS_LABELS).map(([value, label]) => (
                    <option key={value} value={value}>{label}</option>
                  ))}
                </select>
              </label>

              <label className="stack stack-tight">
                <span className="label">预估字数</span>
                <input
                  className="input"
                  inputMode="numeric"
                  value={form.estimatedWordCount}
                  onChange={(event) => setField("estimatedWordCount", event.target.value)}
                  placeholder="可选"
                />
              </label>

              <label className="stack stack-tight">
                <span className="label">实际字数</span>
                <input
                  className="input"
                  inputMode="numeric"
                  value={form.actualWordCount}
                  onChange={(event) => setField("actualWordCount", event.target.value)}
                  placeholder="可选"
                />
              </label>
            </div>

            <label className="stack stack-tight">
              <span className="label">节点内容</span>
              <textarea
                className="textarea"
                value={form.content}
                onChange={(event) => setField("content", event.target.value)}
                placeholder="写清楚这个阶段/单元/章节组的目标、冲突、高潮、结果和遗留钩子。"
                rows={8}
              />
            </label>

            <div className="row row-between">
              <div className="outline-feedback">
                {error ? <span className="status-text error">{error}</span> : null}
                {message ? <span className="status-text success">{message}</span> : null}
              </div>
              <button className="button" type="button" onClick={handleSaveNode} disabled={pending}>
                {pending ? "保存中..." : form.id ? "保存节点" : "创建节点"}
              </button>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
