"use client";

import { useEffect, useMemo, useState } from "react";
import Image from "next/image";

import { flattenFormalShots } from "./adaptation-state";
import type {
  FormalPlan,
  FormalShot,
  KeyframeRole,
  PostProductionWorkspace,
} from "./types";

const ROLES: KeyframeRole[] = ["initial_state", "transition_anchor", "end_state"];
const ROLE_LABEL: Record<KeyframeRole, string> = {
  initial_state: "首帧",
  transition_anchor: "过渡锚点",
  end_state: "尾帧",
};

type Props = {
  plan: FormalPlan;
  selectedShot: FormalShot | null;
  workspace: PostProductionWorkspace | null;
  working: string | null;
  onSelectShot: (shotKey: string) => void;
  onBind: (role: KeyframeRole, assetId: string | null) => void;
  onExtract: (role: KeyframeRole, takeId: string, timestampMs: number) => void;
  onUpload: (role: KeyframeRole, file: File) => void;
};

export function KeyframeWorkspace({
  plan,
  selectedShot,
  workspace,
  working,
  onSelectShot,
  onBind,
  onExtract,
  onUpload,
}: Props) {
  const shots = useMemo(() => flattenFormalShots(plan), [plan]);
  const shotWorkspace = workspace?.shots.find((item) => item.shotId === selectedShot?.id);
  const productionShot = workspace?.episodes
    .flatMap((episode) => episode.shots)
    .find((shot) => shot.shotId === selectedShot?.id);
  const [selectedAssets, setSelectedAssets] = useState<Record<KeyframeRole, string>>({
    initial_state: "",
    transition_anchor: "",
    end_state: "",
  });
  const [takeId, setTakeId] = useState("");
  const [timestampMs, setTimestampMs] = useState(0);

  useEffect(() => {
    const next = Object.fromEntries(ROLES.map((role) => {
      const head = shotWorkspace?.heads.find((item) => item.role === role);
      return [role, head?.currentVersion?.asset?.id ?? ""];
    })) as Record<KeyframeRole, string>;
    const timer = window.setTimeout(() => {
      setSelectedAssets(next);
      setTakeId(productionShot?.confirmedTakeId ?? productionShot?.takes[0]?.id ?? "");
      setTimestampMs(0);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [productionShot?.confirmedTakeId, productionShot?.takes, shotWorkspace]);

  if (!workspace) {
    return <div className="chapter-adaptation-empty"><strong>正在加载关键帧工作区...</strong></div>;
  }
  if (!selectedShot || !shotWorkspace) {
    return <div className="chapter-adaptation-empty"><strong>请选择一个正式镜头</strong></div>;
  }

  const issues = workspace.continuityIssues.filter((issue) => issue.shotIds.includes(selectedShot.id));
  const busy = working !== null;
  return (
    <div className="post-production-layout">
      <aside className="post-production-shot-list">
        <div className="post-production-section-title"><strong>正式镜头</strong><span>{shots.length} 镜</span></div>
        {shots.map((shot) => {
          const configured = workspace.shots.find((item) => item.shotId === shot.id)
            ?.heads.some((head) => Boolean(head.currentVersion?.asset));
          return (
            <button
              className={shot.id === selectedShot.id ? "active" : ""}
              key={shot.id}
              type="button"
              onClick={() => onSelectShot(shot.shotKey)}
            >
              <span>{shot.shotKey}</span><strong>{shot.title}</strong><small>{configured ? "有视觉锚点" : "纯提示词"}</small>
            </button>
          );
        })}
      </aside>
      <main className="keyframe-main">
        <header className="post-production-context-header">
          <div><span>{selectedShot.shotKey}</span><h3>{selectedShot.title}</h3></div>
          <p>关键帧是可选的镜头画面锚点；确认后只进入下一次新渲染，不改变已有 Take。</p>
        </header>
        {issues.length ? (
          <div className="continuity-issues">
            {issues.map((issue) => <div className={`continuity-issue ${issue.severity}`} key={`${issue.code}:${issue.shotIds.join(":")}`}><strong>{issue.severity === "blocking" ? "阻断" : issue.severity === "warning" ? "复核" : "建议"}</strong><span>{issue.message}</span></div>)}
          </div>
        ) : <div className="notice notice-success">当前没有检测到可解释的连续性冲突。</div>}
        <div className="keyframe-role-grid">
          {ROLES.map((role) => {
            const head = shotWorkspace.heads.find((item) => item.role === role);
            const current = head?.currentVersion?.asset ?? null;
            return (
              <section className="keyframe-role" key={role}>
                <header><strong>{ROLE_LABEL[role]}</strong><span>revision {head?.revision ?? 1}</span></header>
                <div className="keyframe-preview">
                  {current ? <Image src={current.contentUrl} alt={`${selectedShot.title} ${ROLE_LABEL[role]}`} fill unoptimized sizes="320px" /> : <span>未设置</span>}
                </div>
                {head?.history?.length ? (
                  <div className="keyframe-history">
                    <div><strong>版本历史</strong><span>恢复会创建新版本，不覆盖旧记录</span></div>
                    <div className="keyframe-history-list">
                      {(head.history ?? []).map((version) => {
                        const assetAvailable = !version.asset || workspace.keyframeAssets.some((asset) => asset.id === version.asset?.id);
                        return <button
                          className={version.id === head.currentVersion?.id ? "active" : ""}
                          key={version.id}
                          type="button"
                          disabled={busy || version.id === head.currentVersion?.id || !assetAvailable}
                          onClick={() => onBind(role, version.asset?.id ?? null)}
                        >
                          <span className="keyframe-history-thumb">
                            {version.asset ? <Image src={version.asset.contentUrl} alt={`${ROLE_LABEL[role]} v${version.versionNo}`} fill unoptimized sizes="64px" /> : <i>已清除</i>}
                          </span>
                          <strong>v{version.versionNo}</strong>
                          <small>{!assetAvailable ? "素材授权已失效" : version.sourceKind === "take_frame" ? `Take 抽帧 · ${(version.sourceTimeMs ?? 0) / 1000}s` : version.sourceKind === "asset" ? "图片素材" : "清除版本"}</small>
                        </button>;
                      })}
                    </div>
                  </div>
                ) : null}
                <label>从已锁定图片选择
                  <select
                    className="select"
                    value={selectedAssets[role]}
                    disabled={busy}
                    onChange={(event) => setSelectedAssets((state) => ({ ...state, [role]: event.target.value }))}
                  >
                    <option value="">不使用关键帧</option>
                    {workspace.keyframeAssets.map((asset) => <option key={asset.id} value={asset.id}>{asset.name}</option>)}
                  </select>
                </label>
                <div className="inline-actions">
                  <button className="button primary sm" type="button" disabled={busy || selectedAssets[role] === (current?.id ?? "")} onClick={() => onBind(role, selectedAssets[role] || null)}>确认采用</button>
                  <label className="button secondary sm file-button">上传并采用
                    <input type="file" accept="image/png,image/jpeg,image/webp" disabled={busy} onChange={(event) => {
                      const file = event.target.files?.[0];
                      if (file) onUpload(role, file);
                      event.currentTarget.value = "";
                    }} />
                  </label>
                </div>
                <div className="keyframe-extract-controls">
                  <strong>从 Take 抽帧</strong>
                  <select className="select" value={takeId} disabled={busy || !productionShot?.takes.length} onChange={(event) => setTakeId(event.target.value)}>
                    <option value="">选择 Take</option>
                    {productionShot?.takes.map((take) => <option key={take.id} value={take.id}>Take {take.takeNo} · {take.durationMs ? `${(take.durationMs / 1000).toFixed(1)}s` : "时长未知"}</option>)}
                  </select>
                  <label>时间点（秒）<input className="input" type="number" min={0} step={0.1} value={timestampMs / 1000} onChange={(event) => setTimestampMs(Math.round(Number(event.target.value) * 1000))} /></label>
                  <button className="button ghost sm" type="button" disabled={busy || !takeId || !workspace.readiness.ffmpegAvailable} onClick={() => onExtract(role, takeId, timestampMs)}>抽帧并采用</button>
                </div>
              </section>
            );
          })}
        </div>
      </main>
    </div>
  );
}
