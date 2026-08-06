"use client";

import type { components } from "@inkforge/api-client";
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { browserApi } from "@/lib/api/browser";
import { createClientRequestId } from "@/lib/api/client-request-id";
import { ApiResponseError, requireApiData } from "@/lib/api/response";
import {
  captureEditBaseline,
  requireEditBaseline,
  type EditBaseline,
} from "@/features/workspace/edit-baseline";
import {
  advanceReferenceCreateIdentity,
  buildReferenceDeleteBody,
  buildReferenceUpdateBody,
  createReferenceMutationState,
} from "./reference-mutation-state";

type ReferenceDto = components["schemas"]["ReferenceDto"];
type ReferenceType = ReferenceDto["type"];

type ReferencePanelProps = {
  novelId: string;
  references: ReferenceDto[];
  onChanged?: () => void;
};

const RAG_LABELS: Record<ReferenceDto["ragStatus"], string> = {
  disabled: "等待索引",
  ready: "索引就绪",
  failed: "索引失败",
};

export function ReferencePanel({ novelId, references, onChanged }: ReferencePanelProps) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editBaseline, setEditBaseline] = useState<EditBaseline<ReferenceDto> | null>(null);
  const [title, setTitle] = useState("");
  const [type, setType] = useState<ReferenceType>("note");
  const [content, setContent] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [mutation, setMutation] = useState(
    () => createReferenceMutationState(createClientRequestId),
  );
  const [saveError, setSaveError] = useState<string | null>(null);

  const resetForm = () => {
    setEditingId(null);
    setEditBaseline(null);
    setTitle("");
    setType("note");
    setContent("");
    setSourceUrl("");
  };

  const refresh = () => {
    onChanged?.();
    router.refresh();
  };

  const showError = (error: unknown) => {
    setSaveError(
      error instanceof ApiResponseError && error.status === 409
        ? "参考资料已在其他位置更新，当前表单已保留，请刷新后重试。"
        : error instanceof Error ? error.message : "参考资料操作失败，请稍后重试。",
    );
  };

  const handleSubmit = () => {
    startTransition(async () => {
      setSaveError(null);
      try {
        const baseline = requireEditBaseline(editingId, editBaseline);
        if (editingId !== null) {
          if (!baseline) throw new Error("编辑基线缺失，不能保存");
          requireApiData(await browserApi.PATCH(
            "/api/v1/novels/{novel_id}/references/{reference_id}",
            {
              params: { path: { novel_id: novelId, reference_id: baseline.id } },
              body: buildReferenceUpdateBody(baseline, {
                title,
                type,
                content,
                sourceUrl: sourceUrl || null,
              }),
            },
          ));
        } else {
          requireApiData(await browserApi.POST("/api/v1/novels/{novel_id}/references", {
            params: { path: { novel_id: novelId } },
            body: {
              title,
              type,
              content,
              sourceUrl: sourceUrl || null,
              clientRequestId: mutation.clientRequestId,
            },
          }));
          setMutation((current) => advanceReferenceCreateIdentity(
            current,
            true,
            createClientRequestId,
          ));
        }
        resetForm();
        refresh();
      } catch (error) {
        showError(error);
      }
    });
  };

  const handleEdit = (reference: ReferenceDto) => {
    setSaveError(null);
    setEditBaseline(captureEditBaseline(reference));
    setEditingId(reference.id);
    setTitle(reference.title);
    setType(reference.type);
    setContent(reference.content);
    setSourceUrl(reference.sourceUrl ?? "");
  };

  const handleDelete = (reference: ReferenceDto) => {
    startTransition(async () => {
      setSaveError(null);
      try {
        const target = editingId === reference.id
          ? requireEditBaseline(editingId, editBaseline)
          : reference;
        if (!target) throw new Error("编辑基线缺失，不能删除");
        requireApiData(await browserApi.DELETE(
          "/api/v1/novels/{novel_id}/references/{reference_id}",
          {
            params: { path: { novel_id: novelId, reference_id: target.id } },
            body: buildReferenceDeleteBody(target),
          },
        ));
        if (editingId === reference.id) resetForm();
        refresh();
      } catch (error) {
        showError(error);
      }
    });
  };

  return (
    <div className="panel">
      <div className="panel-header">
        <div>
          <h3 className="title-md">参考资料</h3>
          <p className="muted">把世界观草稿、网页摘要、资料笔记集中存放</p>
        </div>
      </div>
      <div className="panel-body stack">
        <input className="input" placeholder="资料标题" value={title} onChange={(event) => setTitle(event.target.value)} />
        <select className="select" value={type} onChange={(event) => setType(event.target.value as ReferenceType)}>
          <option value="note">笔记</option>
          <option value="web">网页</option>
          <option value="book">书籍</option>
          <option value="image">图片</option>
          <option value="custom">其他</option>
        </select>
        <textarea className="textarea" placeholder="资料内容" value={content} onChange={(event) => setContent(event.target.value)} />
        <input className="input" placeholder="来源链接（可选）" value={sourceUrl} onChange={(event) => setSourceUrl(event.target.value)} />
        <div className="row row-end">
          {editingId ? <button className="button secondary" type="button" disabled={pending} onClick={resetForm}>取消编辑</button> : null}
          <button className="button secondary" type="button" disabled={pending} onClick={handleSubmit}>
            {pending ? "保存中..." : editingId ? "保存参考资料" : "新增参考资料"}
          </button>
        </div>
        {saveError ? <p className="form-error" role="alert">{saveError}</p> : null}

        <div className="list">
          {references.length ? references.map((item) => (
            <div key={item.id} className="list-item">
              <div className="row row-between">
                <div className="meta">
                  <span className="badge">{item.type}</span>
                  <strong>{item.title}</strong>
                  <span className={`badge ${item.ragStatus === "ready" ? "badge-success" : item.ragStatus === "failed" ? "badge-warning" : ""}`}>
                    {RAG_LABELS[item.ragStatus]}
                  </span>
                </div>
                <div className="row">
                  <button className="button secondary sm" type="button" disabled={pending} onClick={() => handleEdit(item)}>编辑</button>
                  <button className="button secondary sm" type="button" disabled={pending} onClick={() => handleDelete(item)}>删除</button>
                </div>
              </div>
              <div className="muted">{item.content}</div>
              {item.errorMessage ? <div className="form-error">{item.errorMessage}</div> : null}
              {item.sourceUrl ? <a href={item.sourceUrl} target="_blank" rel="noreferrer" className="muted">{item.sourceUrl}</a> : null}
            </div>
          )) : <div className="empty">还没有参考资料，可以把世界观草稿先贴进来。</div>}
        </div>
      </div>
    </div>
  );
}
