"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTransition } from "react";

import { browserApi } from "@/lib/api/browser";
import { requireApiData } from "@/lib/api/response";

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

  const handleApply = (styleId: string) => {
    startTransition(async () => {
      requireApiData(await browserApi.PATCH("/api/v1/novels/{novel_id}/applied-style", {
        params: { path: { novel_id: novelId } },
        body: { styleId },
      }));

      onChanged?.();
      router.refresh();
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
                      <span className="badge badge-info">
                        当前使用
                      </span>
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
      </div>
    </div>
  );
}
