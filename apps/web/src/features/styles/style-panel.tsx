"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { browserApi } from "@/lib/api/browser";
import { ApiResponseError, requireApiData } from "@/lib/api/response";
import { buildApplyStyleBody } from "./style-mutation";

type StylePanelProps = {
  novelId: string;
  appliedStyleId: string | null;
  styles: Array<{
    id: string;
    name: string;
    portraitMarkdown?: string | null;
    sourceType: string;
  }>;
  onChanged?: () => void;
};

export function StylePanel({ novelId, appliedStyleId, styles, onChanged }: StylePanelProps) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [saveError, setSaveError] = useState<string | null>(null);

  const handleApply = (styleId: string | null) => {
    startTransition(async () => {
      setSaveError(null);
      try {
        requireApiData(await browserApi.PATCH("/api/v1/novels/{novel_id}/applied-style", {
          params: { path: { novel_id: novelId } },
          body: buildApplyStyleBody(styleId, appliedStyleId),
        }));
        onChanged?.();
        router.refresh();
      } catch (error) {
        setSaveError(
          error instanceof ApiResponseError && error.status === 409
            ? "文风已在其他位置更新，当前操作已保留，请刷新后重试。"
            : error instanceof Error ? error.message : "文风操作失败，请稍后重试。",
        );
      }
    });
  };

  return (
    <div className="panel">
      <div className="panel-header">
        <div>
          <h3 className="title-md">文风</h3>
          <p className="muted">选择已生成画像的文风应用到当前小说</p>
        </div>
      </div>
      <div className="panel-body stack">
        <Link href="/styles" className="button secondary">
          前往文风库管理
        </Link>

        <div className="list">
          {styles.length ? (
            styles.map((style) => {
              const hasPortrait = Boolean(style.portraitMarkdown);
              const isApplied = style.id === appliedStyleId;

              return (
                <div key={style.id} className="list-item">
                  <div className="row row-between">
                    <div className="stack stack-tight">
                      <div className="meta">
                        <strong>{style.name}</strong>
                        {hasPortrait && (
                          <span className="badge badge-success">
                            已生成画像
                          </span>
                        )}
                        {!hasPortrait && (
                          <span className="badge badge-warning">
                            未生成画像
                          </span>
                        )}
                      </div>
                      <div className="muted small-text">
                        {hasPortrait
                          ? "包含创作方法论、独特标记、生成风格、表达特征、风格特质"
                          : "请前往文风库上传参考资料并生成画像"}
                      </div>
                    </div>
                    {isApplied ? (
                      <div className="row">
                        <span className="badge badge-info">当前使用</span>
                        <button
                          className="button secondary sm"
                          type="button"
                          onClick={() => handleApply(null)}
                          disabled={pending}
                        >
                          {pending ? "处理中..." : "清除"}
                        </button>
                      </div>
                    ) : (
                      <button
                        className="button sm"
                        type="button"
                        onClick={() => handleApply(style.id)}
                        disabled={pending || !hasPortrait}
                      >
                        {pending ? "应用中..." : "应用"}
                      </button>
                    )}
                  </div>
                </div>
              );
            })
          ) : (
            <div className="empty">还没有文风，请先去文风库创建。</div>
          )}
        </div>
        {saveError ? <p className="form-error" role="alert">{saveError}</p> : null}
      </div>
    </div>
  );
}
