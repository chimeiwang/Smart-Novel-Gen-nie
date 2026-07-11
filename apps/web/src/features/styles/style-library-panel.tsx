"use client";

import { useState, useRef } from "react";

import {
  createWritingStyleAction,
  deleteStyleReferenceAction,
  deleteWritingStyleAction,
  uploadStyleReferenceAction,
  updateStyleSectionAction,
} from "@/app/actions";
import { ParagraphText } from "@/features/writing/plain-text";

type StyleReference = {
  id: string;
  filename: string;
  charCount: number;
  status: string;
};

type StyleItem = {
  id: string;
  name: string;
  sourceType: string;
  creativeMethodology: string | null;
  uniqueMarkers: string | null;
  generationStyle: string | null;
  expressionFeatures: string | null;
  styleTraits: string | null;
  portraitMarkdown: string | null;
  originalCharCount: number;
  usedCharCount: number;
  truncated: boolean;
  errorMessage: string | null;
  references: StyleReference[];
};

type StyleLibraryPanelProps = {
  styles: StyleItem[];
};

const SECTIONS = [
  { key: "creativeMethodology", label: "创作方法论" },
  { key: "uniqueMarkers", label: "独特标记" },
  { key: "generationStyle", label: "生成风格" },
  { key: "expressionFeatures", label: "表达特征" },
  { key: "styleTraits", label: "风格特质" },
] as const;

type SectionKey = (typeof SECTIONS)[number]["key"];

type SectionState = {
  status: "idle" | "generating" | "done" | "error";
  content: string;
  error?: string;
};

type EditState = {
  section: SectionKey;
  content: string;
};

export function StyleLibraryPanel({ styles: initialStyles }: StyleLibraryPanelProps) {
  const [styles, setStyles] = useState<StyleItem[]>(initialStyles);
  const [newStyleName, setNewStyleName] = useState("");
  const [expandedStyleId, setExpandedStyleId] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);

  // 生成状态
  const [sectionStates, setSectionStates] = useState<Record<string, Record<SectionKey, SectionState>>>({});
  const abortControllerRef = useRef<AbortController | null>(null);

  // 编辑状态
  const [editingStyleId, setEditingStyleId] = useState<string | null>(null);
  const [editState, setEditState] = useState<EditState | null>(null);
  const [saving, setSaving] = useState(false);

  const getSectionContent = (style: StyleItem, key: SectionKey): string => {
    const state = sectionStates[style.id]?.[key];
    if (state) return state.content;
    return style[key] || "";
  };

  const getSectionStatus = (style: StyleItem, key: SectionKey): SectionState["status"] => {
    const state = sectionStates[style.id]?.[key];
    if (state?.status) return state.status;
    if (style[key]) return "done";
    return "idle";
  };

  const isGeneratingAny = (style: StyleItem): boolean => {
    const state = sectionStates[style.id];
    if (!state) return false;
    return SECTIONS.some((s) => state[s.key]?.status === "generating");
  };

  const isEditing = (styleId: string, section: SectionKey): boolean => {
    return editingStyleId === styleId && editState?.section === section;
  };

  // 创建文风
  const handleCreateStyle = async () => {
    const result = await createWritingStyleAction({ name: newStyleName });
    if (result) {
      const newStyle: StyleItem = {
        id: result.styleId,
        name: newStyleName || "新文风",
        sourceType: "agent",
        creativeMethodology: null,
        uniqueMarkers: null,
        generationStyle: null,
        expressionFeatures: null,
        styleTraits: null,
        portraitMarkdown: null,
        originalCharCount: 0,
        usedCharCount: 0,
        truncated: false,
        errorMessage: null,
        references: [],
      };
      setStyles([newStyle, ...styles]);
      setExpandedStyleId(result.styleId);
      setNewStyleName("");
    }
  };

  // 上传文件
  const handleUploadFile = async (styleId: string, file: File) => {
    setUploadError(null);

    if (!file.name.endsWith(".txt")) {
      setUploadError("只支持 .txt 文件");
      return;
    }

    const sizeMB = file.size / (1024 * 1024);
    if (sizeMB > 50) {
      setUploadError(`文件过大（${sizeMB.toFixed(1)}MB），最大 50MB`);
      return;
    }

    try {
      const content = await file.text();
      const result = await uploadStyleReferenceAction({ styleId, filename: file.name, content });

      if (result.success) {
        setStyles((prev) =>
          prev.map((s) => {
            if (s.id === styleId) {
              return {
                ...s,
                references: [{ id: result.referenceId, filename: file.name, charCount: result.charCount, status: "ready" }, ...s.references],
              };
            }
            return s;
          }),
        );
      } else {
        setUploadError(result.error);
      }
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : "上传失败");
    }
  };

  // 删除文件
  const handleDeleteFile = async (styleId: string, referenceId: string) => {
    await deleteStyleReferenceAction({ styleId, referenceId });
    setStyles((prev) =>
      prev.map((s) => {
        if (s.id === styleId) {
          return { ...s, references: s.references.filter((r) => r.id !== referenceId) };
        }
        return s;
      }),
    );
  };

  // 删除文风
  const handleDeleteStyle = async (styleId: string) => {
    if (!confirm("确定要删除此文风吗？")) return;
    await deleteWritingStyleAction({ styleId });
    setStyles((prev) => prev.filter((s) => s.id !== styleId));
    if (expandedStyleId === styleId) setExpandedStyleId(null);
  };

  // 生成单个维度
  const generateSection = async (styleId: string, section: SectionKey) => {
    setSectionStates((prev) => ({
      ...prev,
      [styleId]: { ...prev[styleId], [section]: { status: "generating", content: "" } },
    }));

    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    try {
      const response = await fetch("/api/portrait/section", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ styleId, section }),
        signal: abortController.signal,
      });

      if (!response.ok) throw new Error(`请求失败: ${response.status}`);

      const reader = response.body?.getReader();
      if (!reader) throw new Error("无法读取响应");

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;

          try {
            const data = JSON.parse(line.slice(6));

            if (data.type === "chunk") {
              setSectionStates((prev) => ({
                ...prev,
                [styleId]: {
                  ...prev[styleId],
                  [section]: {
                    status: "generating",
                    content: (prev[styleId]?.[section]?.content || "") + data.content,
                  },
                },
              }));
            } else if (data.type === "done") {
              setSectionStates((prev) => ({
                ...prev,
                [styleId]: { ...prev[styleId], [section]: { status: "done", content: data.content } },
              }));
              setStyles((prev) => prev.map((s) => (s.id === styleId ? { ...s, [section]: data.content } : s)));
            } else if (data.type === "error") {
              setSectionStates((prev) => ({
                ...prev,
                [styleId]: { ...prev[styleId], [section]: { status: "error", content: "", error: data.message } },
              }));
            }
          } catch {}
        }
      }
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") {
        setSectionStates((prev) => ({
          ...prev,
          [styleId]: { ...prev[styleId], [section]: { status: "idle", content: "" } },
        }));
      } else {
        setSectionStates((prev) => ({
          ...prev,
          [styleId]: {
            ...prev[styleId],
            [section]: { status: "error", content: "", error: error instanceof Error ? error.message : "生成失败" },
          },
        }));
      }
    }
  };

  // 生成所有维度
  const generateAllSections = async (styleId: string) => {
    for (const section of SECTIONS) {
      const currentStatus = getSectionStatus(styles.find((s) => s.id === styleId)!, section.key);
      if (currentStatus !== "done") {
        await generateSection(styleId, section.key);
      }
    }
  };

  // 停止生成
  const stopGeneration = () => {
    abortControllerRef.current?.abort();
  };

  // 开始编辑
  const startEdit = (styleId: string, section: SectionKey) => {
    const style = styles.find((s) => s.id === styleId);
    const content = getSectionContent(style!, section);
    setEditingStyleId(styleId);
    setEditState({ section, content });
  };

  // 取消编辑
  const cancelEdit = () => {
    setEditingStyleId(null);
    setEditState(null);
  };

  // 保存编辑
  const saveEdit = async () => {
    if (!editingStyleId || !editState) return;

    setSaving(true);
    try {
      await updateStyleSectionAction({
        styleId: editingStyleId,
        section: editState.section,
        content: editState.content,
      });

      // 更新本地状态
      setStyles((prev) =>
        prev.map((s) => (s.id === editingStyleId ? { ...s, [editState.section]: editState.content } : s)),
      );

      // 清除编辑状态
      setEditingStyleId(null);
      setEditState(null);
    } finally {
      setSaving(false);
    }
  };

  const getTotalCharCount = (refs: StyleReference[]) => refs.reduce((sum, r) => sum + r.charCount, 0);
  const hasPortrait = (style: StyleItem) => Boolean(style.creativeMethodology || style.uniqueMarkers);

  return (
    <div className="stack">
      {/* 创建文风 */}
      <div className="panel">
        <div className="panel-header">
          <div>
            <h2 className="title-lg">创建文风</h2>
            <p className="muted">创建后上传 .txt 参考资料生成画像</p>
          </div>
        </div>
        <div className="panel-body row">
          <input className="input" placeholder="文风名称" value={newStyleName} onChange={(e) => setNewStyleName(e.target.value)} onKeyDown={(e) => e.key === "Enter" && handleCreateStyle()} />
          <button className="button" type="button" onClick={handleCreateStyle} disabled={!newStyleName.trim()}>创建</button>
        </div>
      </div>

      {/* 文风列表 */}
      <div className="panel">
        <div className="panel-header">
          <h2 className="title-lg">已有文风</h2>
        </div>
        <div className="panel-body">
          {styles.length === 0 ? (
            <div className="empty">还没有文风</div>
          ) : (
            <div className="list">
              {styles.map((style) => (
                <div key={style.id} className="list-item stack">
                  {/* 头部 */}
                  <div className="row row-between">
                    <div className="stack stack-tight">
                      <strong className="title-md">{style.name}</strong>
                      <div className="meta">
                        <span className="badge">{style.references.length} 文件</span>
                        <span className="badge">{getTotalCharCount(style.references).toLocaleString()} 字</span>
                        {hasPortrait(style) && <span className="badge badge-success">已完成</span>}
                      </div>
                    </div>
                    <div className="row">
                      <button className="button ghost" type="button" onClick={() => setExpandedStyleId(expandedStyleId === style.id ? null : style.id)}>
                        {expandedStyleId === style.id ? "收起" : "展开"}
                      </button>
                      <button className="button danger" type="button" onClick={() => handleDeleteStyle(style.id)}>删除</button>
                    </div>
                  </div>

                  {/* 展开内容 */}
                  {expandedStyleId === style.id && (
                    <div className="style-expanded stack">
                      {/* 上传 */}
                      <div className="stack">
                        <strong>上传参考资料（.txt，最大 50MB）</strong>
                        <input type="file" accept=".txt" onChange={(e) => { const file = e.target.files?.[0]; if (file) handleUploadFile(style.id, file); }} />
                      </div>

                      {uploadError && <div className="notice notice-danger">{uploadError}</div>}

                      {/* 文件列表 */}
                      {style.references.length > 0 && (
                        <div className="stack">
                          <strong>已上传</strong>
                          <div className="list">
                            {style.references.map((ref) => (
                              <div key={ref.id} className="style-file-row row row-between">
                                <div>
                                  <span>{ref.filename}</span>
                                  <span className="muted inline-gap">{ref.charCount.toLocaleString()} 字</span>
                                </div>
                                <button className="button ghost sm" type="button" onClick={() => handleDeleteFile(style.id, ref.id)}>删除</button>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* 生成按钮 */}
                      <div className="row">
                        {isGeneratingAny(style) ? (
                          <button className="button" type="button" onClick={stopGeneration}>停止生成</button>
                        ) : (
                          <button className="button" type="button" onClick={() => generateAllSections(style.id)} disabled={style.references.length === 0}>生成画像</button>
                        )}
                        {style.references.length === 0 && <span className="muted">请先上传参考资料</span>}
                      </div>

                      {/* 画像维度 - 完整展示 */}
                      <div className="stack">
                        <strong>画像维度</strong>
                        {SECTIONS.map((section) => {
                          const status = getSectionStatus(style, section.key);
                          const content = getSectionContent(style, section.key);
                          const state = sectionStates[style.id]?.[section.key];
                          const editing = isEditing(style.id, section.key);

                          return (
                            <div key={section.key} className="style-section stack">
                              {/* 标题栏 */}
                              <div className="row row-between">
                                <div className="row row-tight">
                                  <strong className="style-section-title">{section.label}</strong>
                                  {status === "generating" && <span className="badge badge-info">生成中...</span>}
                                  {status === "done" && <span className="badge badge-success">已完成</span>}
                                  {status === "error" && <span className="badge badge-danger">失败</span>}
                                </div>
                                <div className="row row-tight">
                                  {status !== "generating" && style.references.length > 0 && (
                                    <button className="button ghost sm" type="button" onClick={() => generateSection(style.id, section.key)}>
                                      {status === "done" ? "重新生成" : "生成"}
                                    </button>
                                  )}
                                  {content && !editing && (
                                    <button className="button ghost sm" type="button" onClick={() => startEdit(style.id, section.key)}>
                                      编辑
                                    </button>
                                  )}
                                </div>
                              </div>

                              {/* 错误信息 */}
                              {state?.error && <div className="status-text error">{state.error}</div>}

                              {/* 内容区域 */}
                              {editing ? (
                                <div className="stack stack-tight">
                                  <textarea
                                    className="textarea"
                                    value={editState?.content || ""}
                                    onChange={(e) => setEditState((prev) => prev ? { ...prev, content: e.target.value } : null)}
                                  />
                                  <div className="row row-tight">
                                    <button className="button" type="button" onClick={saveEdit} disabled={saving}>
                                      {saving ? "保存中..." : "保存"}
                                    </button>
                                    <button className="button ghost" type="button" onClick={cancelEdit} disabled={saving}>
                                      取消
                                    </button>
                                  </div>
                                </div>
                              ) : content ? (
                                <div className="editor-preview style-preview">
                                  <ParagraphText text={content} />
                                </div>
                              ) : (
                                <div className="muted small-text">暂无内容，点击&quot;生成&quot;按钮生成</div>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
