"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { createNovelAction } from "@/app/actions";

interface CreateNovelModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export function CreateNovelModal({ isOpen, onClose }: CreateNovelModalProps) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [name, setName] = useState("");
  const [summary, setSummary] = useState("");

  const handleSubmit = async (formData: FormData) => {
    setPending(true);
    try {
      const result = await createNovelAction(formData);
      if (result?.novelId) {
        onClose();
        router.push(`/workspace/${result.novelId}`);
      }
    } finally {
      setPending(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2 className="title-lg">开始一个新故事</h2>
          <button className="button ghost icon" type="button" onClick={onClose} title="关闭">
            ×
          </button>
        </div>
        <div className="modal-body">
          <form action={handleSubmit} className="stack">
            <p className="muted">创建小说后，系统会自动生成第一章、默认大纲和剧情进度。</p>
            <label className="stack">
              <span>小说名称</span>
              <input
                className="input"
                name="name"
                placeholder="例如：青云山下有剑仙"
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </label>
            <label className="stack">
              <span>作品简介</span>
              <textarea
                className="textarea"
                name="summary"
                placeholder="写一句故事设定，方便后续大纲和智能写作统一方向"
                value={summary}
                onChange={(e) => setSummary(e.target.value)}
              />
            </label>
            <div className="row">
              <button className="button" type="submit" disabled={pending || !name.trim()}>
                {pending ? "创建中..." : "新建小说"}
              </button>
              <button className="button ghost" type="button" onClick={onClose} disabled={pending}>
                取消
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
