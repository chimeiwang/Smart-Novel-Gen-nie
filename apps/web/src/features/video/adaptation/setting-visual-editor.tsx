"use client";
/* eslint-disable @next/next/no-img-element */

import { useEffect, useRef, useState } from "react";

import { browserApi } from "@/lib/api/browser";
import { createClientRequestId } from "@/lib/api/client-request-id";
import { ApiResponseError, requireApiData } from "@/lib/api/response";
import type { VideoAsset, VisualCanon } from "./types";
import {
  assetPreviewUrl,
  createVisualCandidateDraft,
  currentCanonVersion,
  dutyLabel,
  parseVisualFeatures,
  rebaseVisualCandidateDraft,
  visualDuties,
  type VisualCandidateDraft,
  type VisualSetting,
} from "./visual-canon-state";
import { useVisualEditorLeaveGuard } from "./visual-editor-leave-guard";
import { findUploadedVisualAsset, publishVisualCanonChange } from "./video-project-context";
import "./visual-editor.css";

type Props = {
  novelId: string;
  projectId: string;
  setting: VisualSetting;
  canons: VisualCanon[];
  enabled: boolean;
  onCanonChanged: (canon: VisualCanon) => void;
  onReload: () => Promise<void>;
};

export function SettingVisualEditor({ novelId, projectId, setting, canons, enabled, onCanonChanged, onReload }: Props) {
  const [draft, setDraft] = useState<VisualCandidateDraft | null>(null);
  const [dirty, setDirty] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [rightsConfirmed, setRightsConfirmed] = useState(false);
  const [working, setWorking] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [uploadUncertain, setUploadUncertain] = useState(false);
  const [candidateConflict, setCandidateConflict] = useState(false);
  const uploaded = useRef<{ file: File; duty: VisualCanon["duty"]; asset: VideoAsset } | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const busy = working !== null;
  const slots = canons.filter((canon) => canon.projectId === projectId && canon.settingKind === setting.kind && canon.settingId === setting.id);

  useVisualEditorLeaveGuard(novelId, dirty, busy);
  useEffect(() => {
    if (!file) return;
    const url = URL.createObjectURL(file);
    const timer = window.setTimeout(() => setPreviewUrl(url), 0);
    return () => { window.clearTimeout(timer); URL.revokeObjectURL(url); };
  }, [file]);

  const clearDraft = () => {
    setDraft(null);
    setDirty(false);
    setFile(null);
    setPreviewUrl(null);
    setRightsConfirmed(false);
    setUploadUncertain(false);
    setCandidateConflict(false);
    uploaded.current = null;
  };

  const confirmDraftChange = () => !busy && (!dirty || window.confirm("放弃当前未提交的定妆修改？已保存的候选与正式版本会保留。"));

  const beginDraft = (duty: VisualCanon["duty"], canon?: VisualCanon) => {
    if (!enabled || !confirmDraftChange()) return;
    const requestId = createClientRequestId();
    clearDraft();
    setError(null);
    setNotice(null);
    setDraft(createVisualCandidateDraft(duty, requestId, canon));
  };

  const updateDraft = (patch: Partial<VisualCandidateDraft>) => {
    setDraft((current) => current ? { ...current, ...patch } : current);
    setDirty(true);
  };

  const reloadAfterError = async (failure: unknown, fallback: string) => {
    const message = failure instanceof Error ? failure.message : fallback;
    setError(failure instanceof ApiResponseError && failure.status === 409
      ? `${message}。正在回读最新状态；本地未提交内容已保留，请核对后操作。`
      : message);
    try { await onReload(); } catch { /* 原错误和本地输入保留，作者仍可显式刷新。 */ }
  };

  const saveCandidate = async () => {
    if (!draft || !file || !enabled || busy) return;
    setError(null);
    setNotice(null);
    if (!rightsConfirmed) return setError("请先确认你拥有这张图片的使用权。");
    if (!draft.label.trim()) return setError("请填写定妆或变体名称。");
    if (Array.from(draft.label.trim()).length > 120) return setError("定妆名称最多 120 字。");
    if (file.size > 30 * 1024 * 1024) return setError("图片不能超过 30 MiB。");
    if (!["image/png", "image/jpeg", "image/webp"].includes(file.type)) return setError("请选择 PNG、JPEG 或 WebP 图片。");
    let includeFeatures: string[];
    let excludeFeatures: string[];
    try {
      includeFeatures = parseVisualFeatures(draft.includeFeatures);
      excludeFeatures = parseVisualFeatures(draft.excludeFeatures);
    } catch (validationError) {
      return setError(validationError instanceof Error ? validationError.message : "请检查视觉特征。");
    }
    setWorking("正在核对图片…");
    try {
      let asset = uploaded.current?.file === file && uploaded.current.duty === draft.duty ? uploaded.current.asset : null;
      if (!asset) {
        const digest = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
        const sha256 = Array.from(new Uint8Array(digest), (value) => value.toString(16).padStart(2, "0")).join("");
        // 先回读同一项目中的相同文件；多步骤中断后再次提交不会重复上传已确认收到的图片。
        asset = await findUploadedVisualAsset(projectId, sha256, draft.duty);
        if (!asset && uploadUncertain) {
          throw new Error("仍未查到这张图片的上传结果，请稍后再核对。系统没有自动重复上传。");
        }
        if (!asset) {
          setWorking("正在上传图片…");
          try {
            asset = requireApiData(await browserApi.POST("/api/v1/video/projects/{project_id}/assets", {
              params: { path: { project_id: projectId } },
              body: { file: file as unknown as string, name: `${setting.name} · ${draft.label.trim()}`, modality: "image", duty: draft.duty, sourceKind: "user_upload" },
              bodySerializer: () => {
                const body = new FormData();
                body.append("file", file);
                body.append("name", `${setting.name} · ${draft.label.trim()}`);
                body.append("modality", "image");
                body.append("duty", draft.duty);
                body.append("sourceKind", "user_upload");
                return body;
              },
            }));
          } catch (uploadError) {
            if (!(uploadError instanceof ApiResponseError) || uploadError.status >= 500) setUploadUncertain(true);
            throw uploadError;
          }
        }
        uploaded.current = { file, duty: draft.duty, asset };
        setUploadUncertain(false);
      }
      setWorking("正在确认素材使用权…");
      requireApiData(await browserApi.PATCH("/api/v1/video/assets/{asset_id}/rights", {
        params: { path: { asset_id: asset.id } }, body: { rightsStatus: "confirmed" },
      }));
      setWorking("正在保存定妆候选…");
      const canon = requireApiData(await browserApi.POST("/api/v1/video/projects/{project_id}/visual-canons", {
        params: { path: { project_id: projectId } },
        body: {
          clientRequestId: draft.clientRequestId,
          expectedRevision: draft.expectedRevision,
          settingKind: setting.kind,
          settingId: setting.id,
          duty: draft.duty,
          variantKey: draft.variantKey,
          label: draft.label.trim(),
          candidateAssetId: asset.id,
          includeFeatures,
          excludeFeatures,
          defaultStrength: draft.defaultStrength,
        },
      }));
      onCanonChanged(canon);
      clearDraft();
      setNotice("候选已保存，可以安全刷新。核对图片后点击“确认为定妆”才能用于新的镜头参考。");
      publishVisualCanonChange(projectId);
    } catch (saveError) {
      if (saveError instanceof ApiResponseError && saveError.code === "VIDEO_VISUAL_CANON_REVISION_CONFLICT") setCandidateConflict(true);
      await reloadAfterError(saveError, "保存定妆候选失败，请核对后重试。");
    } finally {
      setWorking(null);
    }
  };

  const approve = async (canon: VisualCanon) => {
    if (!canon.candidateAsset || !enabled || busy) return;
    setError(null);
    setNotice(null);
    setWorking(`approve:${canon.id}`);
    try {
      const approved = requireApiData(await browserApi.POST("/api/v1/video/visual-canons/{canon_id}/approve", {
        params: { path: { canon_id: canon.id } },
        body: { clientRequestId: createClientRequestId(), expectedRevision: canon.revision, candidateAssetId: canon.candidateAsset.id },
      }));
      onCanonChanged(approved);
      setNotice("定妆已确认。已绑定镜头继续使用原版本；请在镜头参考中明确选择新版。");
      publishVisualCanonChange(projectId);
    } catch (approveError) {
      await reloadAfterError(approveError, "确认定妆失败。");
    } finally {
      setWorking(null);
    }
  };

  return (
    <section className="setting-visual-editor" aria-label={`${setting.name}的视觉定妆`}>
      <header className="setting-visual-heading">
        <div><h3>{setting.name} · 视觉定妆</h3><p>{setting.summary || "先确认角色、场景或道具的固定形象，再由镜头选择具体版本。"}</p></div>
        <div className="setting-visual-actions">{visualDuties(setting.kind).map((duty) => <button className="button secondary sm" type="button" key={duty} disabled={!enabled || busy} onClick={() => beginDraft(duty)}>+ 新建{dutyLabel(duty).replace("图", "变体")}</button>)}</div>
      </header>
      {!enabled ? <div className="notice notice-warning">当前环境未开放视频写入，已有定妆与历史版本仍可查看。</div> : null}
      {error ? <div className="notice notice-danger" role="alert">{error}</div> : null}
      {notice ? <div className="notice notice-success" role="status">{notice}</div> : null}
      {!slots.length && !draft ? <div className="setting-visual-empty">还没有定妆。新建一个变体并上传图片；每个版本保存一张图。</div> : null}
      <div className="setting-visual-slots">{slots.map((canon) => {
        const current = currentCanonVersion(canon);
        return (
          <article className="setting-visual-slot" key={canon.id}>
            <header><div><strong>{canon.label}</strong><span>{dutyLabel(canon.duty)} · {current ? `当前 v${current.versionNo}` : "尚未确认"}</span></div><button className="button ghost sm" type="button" disabled={!enabled || busy} onClick={() => beginDraft(canon.duty, canon)}>{canon.candidateAsset ? "替换候选" : "制作新版"}</button></header>
            <div className="setting-visual-images">
              {current ? <figure><img src={assetPreviewUrl(current.asset.id)} alt={`${current.settingName} ${current.label} 当前定妆 v${current.versionNo}`} /><figcaption>当前定妆 v{current.versionNo} · {current.label}</figcaption></figure> : <div className="setting-visual-placeholder">尚无正式定妆</div>}
              {canon.candidateAsset ? <figure className="candidate"><img src={assetPreviewUrl(canon.candidateAsset.id)} alt={`${canon.settingName} ${canon.label} 待确认候选`} /><figcaption>新候选 · 尚未采用</figcaption></figure> : null}
            </div>
            {canon.candidateAsset ? <div className="setting-visual-confirm"><p>保留：{canon.candidateIncludeFeatures.join("、") || "未指定"}</p><p>避免：{canon.candidateExcludeFeatures.join("、") || "未指定"}</p><button className="button primary sm" type="button" disabled={!enabled || busy} onClick={() => void approve(canon)}>{working === `approve:${canon.id}` ? "确认中…" : "确认为定妆"}</button></div> : null}
            {canon.versions.length ? <details className="setting-visual-history"><summary>查看 {canon.versions.length} 个已确认版本</summary><div>{[...canon.versions].sort((left, right) => right.versionNo - left.versionNo).map((version) => <figure key={version.id}><a href={assetPreviewUrl(version.asset.id)} target="_blank" rel="noreferrer"><img src={assetPreviewUrl(version.asset.id)} alt={`${version.settingName} ${version.label} 历史 v${version.versionNo}`} /></a><figcaption><strong>v{version.versionNo}{version.id === canon.currentVersionId ? " · 当前" : ""}</strong><span>{version.label}</span><span>{new Date(version.createdAt).toLocaleString("zh-CN")}</span><span>保留：{version.includeFeatures.join("、") || "未指定"}</span><span>避免：{version.excludeFeatures.join("、") || "未指定"}</span></figcaption></figure>)}</div></details> : null}
          </article>
        );
      })}</div>
      {draft ? <section className="setting-visual-draft" aria-label="定妆候选表单">
        <header><div><h4>{draft.canonId ? "为当前变体制作新版" : "新建独立变体"}</h4><p>{dutyLabel(draft.duty)} · 选择文件后还需保存候选，再明确确认。</p></div><button className="button ghost sm" type="button" disabled={busy} onClick={() => { if (confirmDraftChange()) clearDraft(); }}>放弃未提交修改</button></header>
        {candidateConflict ? <div className="notice notice-warning"><p>这个变体的候选已经变化。上方显示服务器最新状态，下方仍保留你的图片和描述。核对后可继续编辑，再明确保存以替换候选。</p><button className="button secondary sm" type="button" disabled={busy || !slots.some((canon) => canon.duty === draft.duty && canon.variantKey === draft.variantKey && canon.revision !== draft.expectedRevision)} onClick={() => {
          const latest = slots.find((canon) => canon.duty === draft.duty && canon.variantKey === draft.variantKey);
          if (!latest || !window.confirm("保留我的图片和描述，基于上方最新候选继续编辑？再次保存时会替换当前候选，正式定妆仍保持不变。")) return;
          setDraft(rebaseVisualCandidateDraft(draft, latest, createClientRequestId()));
          setCandidateConflict(false);
          setError(null);
        }}>按最新候选继续编辑</button></div> : null}
        <div className="setting-visual-draft-grid">
          <div className="setting-visual-file"><label>参考图片<input key={draft.clientRequestId} ref={fileInput} type="file" accept="image/png,image/jpeg,image/webp" disabled={busy} onChange={(event) => {
            const next = event.target.files?.[0] ?? null;
            setFile(next); setPreviewUrl(null); setDirty(true); setRightsConfirmed(false); setUploadUncertain(false); uploaded.current = null;
          }} /></label>{file && previewUrl ? <img src={previewUrl} alt="尚未保存的本地图片预览" /> : <div className="setting-visual-placeholder">PNG、JPEG 或 WebP，最多 30 MiB</div>}<small>{file ? `${file.name} · 尚未保存为候选` : "尚未选择文件"}</small></div>
          <div className="setting-visual-fields"><label>定妆／变体名称<input className="input" value={draft.label} disabled={busy} onChange={(event) => updateDraft({ label: event.target.value })} placeholder="例如：日常服装、雨夜车站" /></label><label>必须保留特征<textarea className="textarea" value={draft.includeFeatures} disabled={busy} onChange={(event) => updateDraft({ includeFeatures: event.target.value })} placeholder="例如：黑色短发，左眉疤痕。用逗号或换行分隔。" /></label><label>必须避免特征<textarea className="textarea" value={draft.excludeFeatures} disabled={busy} onChange={(event) => updateDraft({ excludeFeatures: event.target.value })} placeholder="例如：现代眼镜，金色长发。用逗号或换行分隔。" /></label><label className="setting-visual-rights"><input type="checkbox" checked={rightsConfirmed} disabled={busy} onChange={(event) => { setRightsConfirmed(event.target.checked); setDirty(true); }} />我确认拥有这张图片的使用权，并允许用于本项目的视频制作参考</label><p className="muted">定妆确认保存参考依据；供应商能否接收素材及生成一致性仍需另行验证。</p></div>
        </div>
        <footer><span>{dirty ? "有未提交内容" : "填写后保存候选"}</span><button className="button primary" type="button" disabled={!enabled || busy || !file || !rightsConfirmed || !draft.label.trim()} onClick={() => void saveCandidate()}>{busy && !working?.startsWith("approve:") ? working : uploadUncertain ? "核对上传结果并保存" : "保存为待确认候选"}</button></footer>
      </section> : null}
    </section>
  );
}
