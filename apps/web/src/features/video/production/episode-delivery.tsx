"use client";

import { useState } from "react";

import { episodeDeliveryContentUrl } from "./production-api";
import type { EpisodeEditVersion, EpisodeExportTask, EpisodeMixVersion, ProductionBaseline, StartEpisodeExportRequest } from "./types";

type Props = {
  episodeId: string;
  baseline: ProductionBaseline;
  edit: EpisodeEditVersion | null;
  mix: EpisodeMixVersion | null;
  tasks: EpisodeExportTask[];
  busy: boolean;
  enabled: boolean;
  onStart: (body: Omit<StartEpisodeExportRequest, "clientRequestId">) => void;
  onRetry: (task: EpisodeExportTask) => void;
};

export function EpisodeDelivery({ episodeId, baseline, edit, mix, tasks, busy, enabled, onStart, onRetry }: Props) {
  const [resolution, setResolution] = useState<"720p" | "1080p">("720p");
  const [framesPerSecond, setFramesPerSecond] = useState<24 | 25 | 30>(24);
  const [burnSubtitles, setBurnSubtitles] = useState(true);
  const [acknowledgedFingerprint, setAcknowledgedFingerprint] = useState<string | null>(null);
  const aligned = Boolean(edit && mix && mix.editVersionId === edit.id);
  const fingerprint = `${baseline.id}:${edit?.id ?? "none"}:${mix?.id ?? "none"}:${resolution}:${framesPerSecond}:${burnSubtitles}`;
  const active = tasks.some((task) => task.status === "pending" || task.status === "rendering");
  return <section className="episode-post-section episode-delivery">
    <header><div><span>制作 v{baseline.versionNo}</span><h3>整集交付</h3><p>每次导出冻结制作基线、粗剪、声音字幕、素材哈希和编码参数；失败重试仍使用原任务清单。</p></div><div><strong>{tasks.filter((task) => task.export).length} 个成片</strong><small>{active ? "导出任务进行中" : "没有活动导出"}</small></div></header>
    <div className="episode-delivery-combination"><span>制作基线<strong>v{baseline.versionNo}</strong><small>{baseline.contentHash.slice(0, 12)}</small></span><span>粗剪<strong>{edit ? `v${edit.versionNo}` : "无"}</strong><small>{edit?.contentHash.slice(0, 12)}</small></span><span>声音字幕<strong>{mix ? `v${mix.versionNo}` : "无"}</strong><small>{mix?.contentHash.slice(0, 12)}</small></span></div>
    {!aligned ? <p className="notice notice-warning">必须先保存绑定当前粗剪的声音字幕版本，不能把不同版本临时拼成导出清单。</p> : null}
    <div className="episode-delivery-controls"><label>清晰度<select className="select" value={resolution} onChange={(event) => setResolution(event.target.value as "720p" | "1080p")}><option value="720p">720p</option><option value="1080p">1080p</option></select></label><label>帧率<select className="select" value={framesPerSecond} onChange={(event) => setFramesPerSecond(Number(event.target.value) as 24 | 25 | 30)}><option value={24}>24 fps</option><option value={25}>25 fps</option><option value={30}>30 fps</option></select></label><label className="episode-baseline-ack"><input type="checkbox" checked={acknowledgedFingerprint === fingerprint} onChange={(event) => setAcknowledgedFingerprint(event.target.checked ? fingerprint : null)} />我已核对上述确切版本组合和输出参数</label><label className="episode-baseline-ack"><input type="checkbox" checked={burnSubtitles} onChange={(event) => setBurnSubtitles(event.target.checked)} />烧录字幕</label><button className="button primary" type="button" disabled={!enabled || !aligned || busy || active || acknowledgedFingerprint !== fingerprint} onClick={() => edit && mix && onStart({ editVersionId: edit.id, mixVersionId: mix.id, resolution, framesPerSecond, burnSubtitles })}>{busy ? "提交中…" : "创建不可变导出任务"}</button></div>
    <div className="episode-export-history">{tasks.map((task) => <article key={task.id}><header><div><strong>{task.export ? `成片 v${task.export.versionNo}` : `任务 ${task.id.slice(-8)}`}</strong><span className={`status ${task.status === "failed" ? "danger" : task.status === "succeeded" ? "" : "warning"}`}>{exportStatus(task.status)}</span></div><small>{task.resolution} · {task.framesPerSecond} fps · {task.burnSubtitles ? "烧录字幕" : "不烧录字幕"} · 尝试 {task.attemptCount}</small></header>{task.lastErrorMessage ? <p className="notice notice-danger">{task.lastErrorMessage}</p> : null}{task.export ? <><video controls preload="metadata" src={episodeDeliveryContentUrl(episodeId, baseline.id, task.export.id)} /><div className="episode-inline-actions"><a className="button ghost sm" download href={episodeDeliveryContentUrl(episodeId, baseline.id, task.export.id)}>下载 MP4</a><span className="muted">输入哈希 {task.inputHash.slice(0, 12)}</span></div></> : null}{task.status === "failed" ? <button className="button ghost sm" type="button" disabled={busy || active} onClick={() => onRetry(task)}>按原清单重试</button> : null}</article>)}{!tasks.length ? <div className="episode-empty compact"><h4>尚无已知导出任务</h4><p>创建成功后会保存任务身份；刷新时只按精确 taskId 回读。</p></div> : null}</div>
  </section>;
}

function exportStatus(status: EpisodeExportTask["status"]): string {
  return { pending: "等待导出", rendering: "正在导出", succeeded: "交付已归档", failed: "导出失败" }[status];
}
