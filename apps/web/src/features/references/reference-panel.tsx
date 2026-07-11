"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { createReferenceMaterialAction } from "@/app/actions";

type ReferencePanelProps = {
  novelId: string;
  references: Array<{
    id: string;
    title: string;
    type: string;
    content: string;
    sourceUrl: string | null;
  }>;
};

export function ReferencePanel({ novelId, references }: ReferencePanelProps) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [title, setTitle] = useState("");
  const [type, setType] = useState<"note" | "web" | "book" | "image" | "custom">("note");
  const [content, setContent] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");

  const handleSubmit = () => {
    startTransition(async () => {
      await createReferenceMaterialAction({
        novelId,
        title,
        type,
        content,
        sourceUrl,
      });

      setTitle("");
      setType("note");
      setContent("");
      setSourceUrl("");
      router.refresh();
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
        <input
          className="input"
          placeholder="资料标题"
          value={title}
          onChange={(event) => setTitle(event.target.value)}
        />
        <select className="select" value={type} onChange={(event) => setType(event.target.value as typeof type)}>
          <option value="note">笔记</option>
          <option value="web">网页</option>
          <option value="book">书籍</option>
          <option value="image">图片</option>
          <option value="custom">其他</option>
        </select>
        <textarea
          className="textarea"
          placeholder="资料内容"
          value={content}
          onChange={(event) => setContent(event.target.value)}
        />
        <input
          className="input"
          placeholder="来源链接（可选）"
          value={sourceUrl}
          onChange={(event) => setSourceUrl(event.target.value)}
        />
        <button className="button secondary" type="button" onClick={handleSubmit}>
          {pending ? "保存中..." : "新增参考资料"}
        </button>

        <div className="list">
          {references.length ? (
            references.map((item) => (
              <div key={item.id} className="list-item">
                <div className="meta">
                  <span className="badge">{item.type}</span>
                  <strong>{item.title}</strong>
                </div>
                <div className="muted">{item.content}</div>
                {item.sourceUrl ? (
                  <a href={item.sourceUrl} target="_blank" rel="noreferrer" className="muted">
                    {item.sourceUrl}
                  </a>
                ) : null}
              </div>
            ))
          ) : (
            <div className="empty">还没有参考资料，可以把世界观草稿先贴进来。</div>
          )}
        </div>
      </div>
    </div>
  );
}
