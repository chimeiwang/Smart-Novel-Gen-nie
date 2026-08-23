"use client";
/* eslint-disable @next/next/no-img-element */

import { useEffect, useMemo, useState } from "react";

import { browserApi } from "@/lib/api/browser";
import { createClientRequestId } from "@/lib/api/client-request-id";
import { requireApiData } from "@/lib/api/response";
import type {
  CharacterSetting,
  FormalPlan,
  FormalShot,
  ItemSetting,
  LocationSetting,
  ShotVisualReferenceSet,
  VisualCanon,
  VisualCanonVersion,
} from "./types";
import {
  assetPreviewUrl,
  currentCanonVersion,
  dutyLabel,
  recommendedVisualReferences,
  visualReferenceWarnings,
  visualShotContext,
  type VisualReferenceSelection,
} from "./visual-canon-state";

type SettingKind = VisualCanon["settingKind"];
type SettingCard = {
  id: string;
  kind: SettingKind;
  name: string;
  summary: string;
};

type VisualCanonPanelProps = {
  novelId: string;
  projectId: string;
  adaptationId: string;
  plan: FormalPlan;
  selectedShot: FormalShot | null;
  canons: VisualCanon[];
  referenceSets: ShotVisualReferenceSet[];
  onSelectShot: (shotKey: string) => void;
  onCanonChanged: (canon: VisualCanon) => void;
  onReferenceSetChanged: (referenceSet: ShotVisualReferenceSet) => void;
};

export function VisualCanonPanel({
  novelId,
  projectId,
  adaptationId,
  plan,
  selectedShot,
  canons,
  referenceSets,
  onSelectShot,
  onCanonChanged,
  onReferenceSetChanged,
}: VisualCanonPanelProps) {
  const [settings, setSettings] = useState<SettingCard[]>([]);
  const [settingsLoading, setSettingsLoading] = useState(true);
  const [selectedSettingKey, setSelectedSettingKey] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [duty, setDuty] = useState<VisualCanon["duty"]>("identity");
  const [variantKey, setVariantKey] = useState("default");
  const [label, setLabel] = useState("标准身份");
  const [includeFeatures, setIncludeFeatures] = useState("");
  const [excludeFeatures, setExcludeFeatures] = useState("");
  const [defaultStrength, setDefaultStrength] = useState(70);
  const [file, setFile] = useState<File | null>(null);
  const [rightsConfirmed, setRightsConfirmed] = useState(false);
  const [selections, setSelections] = useState<VisualReferenceSelection[]>([]);
  const [working, setWorking] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const loadingTimer = window.setTimeout(() => {
      setSettingsLoading(true);
      setError(null);
    }, 0);
    void Promise.all([
      browserApi.GET("/api/v1/novels/{novel_id}/characters", {
        params: { path: { novel_id: novelId } },
      }),
      browserApi.GET("/api/v1/novels/{novel_id}/locations", {
        params: { path: { novel_id: novelId } },
      }),
      browserApi.GET("/api/v1/novels/{novel_id}/items", {
        params: { path: { novel_id: novelId } },
      }),
    ]).then(([charactersResponse, locationsResponse, itemsResponse]) => {
      if (cancelled) return;
      const characters = requireApiData(charactersResponse);
      const locations = requireApiData(locationsResponse);
      const items = requireApiData(itemsResponse);
      const next = [
        ...characters.map(characterSetting),
        ...locations.map(locationSetting),
        ...items.map(itemSetting),
      ];
      setSettings(next);
      setSelectedSettingKey((current) => {
        if (current && next.some((item) => settingKey(item) === current)) return current;
        return next[0] ? settingKey(next[0]) : null;
      });
    }).catch((loadError) => {
      if (!cancelled) setError(errorMessage(loadError, "加载视觉设定卡失败"));
    }).finally(() => {
      if (!cancelled) setSettingsLoading(false);
    });
    return () => {
      cancelled = true;
      window.clearTimeout(loadingTimer);
    };
  }, [novelId]);

  const selectedSetting = settings.find((item) => settingKey(item) === selectedSettingKey) ?? null;
  useEffect(() => {
    const kind = selectedSetting?.kind;
    if (!kind) return;
    const timer = window.setTimeout(() => {
      const nextDuty = kind === "character" ? "identity" : kind === "location" ? "scene" : "prop";
      setDuty(nextDuty);
      setVariantKey("default");
      setLabel(defaultLabel(nextDuty));
      setIncludeFeatures("");
      setExcludeFeatures("");
      setDefaultStrength(70);
      setFile(null);
      setRightsConfirmed(false);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [selectedSetting?.kind, selectedSettingKey]);

  const visibleSettings = useMemo(() => {
    const normalized = search.trim().toLocaleLowerCase("zh-CN");
    if (!normalized) return settings;
    return settings.filter((item) => (
      item.name.toLocaleLowerCase("zh-CN").includes(normalized)
      || item.summary.toLocaleLowerCase("zh-CN").includes(normalized)
    ));
  }, [search, settings]);
  const selectedCanons = canons.filter((canon) => (
    selectedSetting
    && canon.settingKind === selectedSetting.kind
    && canon.settingId === selectedSetting.id
  ));
  const formalShots = useMemo(
    () => plan.scenes.flatMap((scene) => scene.beats.flatMap((beat) => beat.shots)),
    [plan],
  );
  const selectedReferenceSet = selectedShot
    ? referenceSets.find((item) => item.shotId === selectedShot.id) ?? null
    : null;
  const shotContext = selectedShot ? visualShotContext(plan, selectedShot) : "";
  const referenceWarnings = selectedReferenceSet
    ? visualReferenceWarnings(canons, shotContext, selectedReferenceSet.references)
    : [];
  const referenceOptions = buildReferenceOptions(
    canons,
    selectedReferenceSet?.references ?? [],
  );

  useEffect(() => {
    const timer = window.setTimeout(() => setSelections(
      selectedReferenceSet?.references.map((item) => ({
        canonVersionId: item.canonVersionId,
        strength: item.strength,
      })) ?? [],
    ), 0);
    return () => window.clearTimeout(timer);
  }, [selectedReferenceSet]);

  const uploadCandidate = async () => {
    if (!selectedSetting || !file) return setError("请先选择图片文件");
    if (!rightsConfirmed) return setError("请先确认你拥有这张图片的使用权");
    if (file.size > 30 * 1024 * 1024) return setError("图片不能超过 30 MB");
    setWorking("upload");
    setError(null);
    try {
      const asset = requireApiData(await browserApi.POST(
        "/api/v1/video/projects/{project_id}/assets",
        {
          params: { path: { project_id: projectId } },
          body: {
            file: file as unknown as string,
            name: `${selectedSetting.name} · ${label.trim()}`,
            modality: "image",
            duty,
            sourceKind: "user_upload",
          },
          bodySerializer: () => {
            const body = new FormData();
            body.append("file", file);
            body.append("name", `${selectedSetting.name} · ${label.trim()}`);
            body.append("modality", "image");
            body.append("duty", duty);
            body.append("sourceKind", "user_upload");
            return body;
          },
        },
      ));
      requireApiData(await browserApi.PATCH(
        "/api/v1/video/assets/{asset_id}/rights",
        {
          params: { path: { asset_id: asset.id } },
          body: { rightsStatus: "confirmed" },
        },
      ));
      const canon = requireApiData(await browserApi.POST(
        "/api/v1/video/projects/{project_id}/visual-canons",
        {
          params: { path: { project_id: projectId } },
          body: {
            clientRequestId: createClientRequestId(),
            settingKind: selectedSetting.kind,
            settingId: selectedSetting.id,
            duty,
            variantKey: variantKey.trim(),
            label: label.trim(),
            candidateAssetId: asset.id,
            includeFeatures: splitFeatures(includeFeatures),
            excludeFeatures: splitFeatures(excludeFeatures),
            defaultStrength,
          },
        },
      ));
      onCanonChanged(canon);
      setFile(null);
      setRightsConfirmed(false);
    } catch (uploadError) {
      setError(errorMessage(uploadError, "上传视觉设定候选失败"));
    } finally {
      setWorking(null);
    }
  };

  const approveCanon = async (canon: VisualCanon) => {
    if (!canon.candidateAsset) return;
    setWorking(`approve:${canon.id}`);
    setError(null);
    try {
      const approved = requireApiData(await browserApi.POST(
        "/api/v1/video/visual-canons/{canon_id}/approve",
        {
          params: { path: { canon_id: canon.id } },
          body: {
            clientRequestId: createClientRequestId(),
            expectedRevision: canon.revision,
            candidateAssetId: canon.candidateAsset.id,
          },
        },
      ));
      onCanonChanged(approved);
    } catch (approveError) {
      setError(errorMessage(approveError, "确认视觉设定失败"));
    } finally {
      setWorking(null);
    }
  };

  const saveReferences = async () => {
    if (!selectedShot) return;
    setWorking("references");
    setError(null);
    try {
      const result = requireApiData(await browserApi.PUT(
        "/api/v1/video/chapter-adaptations/{adaptation_id}/shots/{shot_id}/visual-references",
        {
          params: { path: { adaptation_id: adaptationId, shot_id: selectedShot.id } },
          body: {
            expectedRevision: selectedReferenceSet?.revision ?? 0,
            references: selections,
          },
        },
      ));
      onReferenceSetChanged(result);
    } catch (saveError) {
      setError(errorMessage(saveError, "保存镜头视觉参考失败"));
    } finally {
      setWorking(null);
    }
  };

  return (
    <div className="visual-canon-grid">
      <section className="visual-canon-settings">
        <header><strong>小说设定卡</strong><span>{settingsLoading ? "加载中" : `${settings.length} 项`}</span></header>
        <input
          className="input"
          type="search"
          value={search}
          disabled={settingsLoading}
          placeholder="搜索角色、地点、道具"
          onChange={(event) => setSearch(event.target.value)}
        />
        <div className="visual-setting-list">
          {settingsLoading ? <div className="empty compact">正在加载角色、地点和道具…</div> : visibleSettings.map((setting) => {
            const slots = canons.filter((canon) => (
              canon.settingKind === setting.kind && canon.settingId === setting.id
            ));
            const approved = slots.filter((canon) => canon.currentVersionId).length;
            const pending = slots.some((canon) => canon.candidateAsset);
            return (
              <button
                className={selectedSettingKey === settingKey(setting) ? "active" : ""}
                key={settingKey(setting)}
                type="button"
                onClick={() => setSelectedSettingKey(settingKey(setting))}
              >
                <span><b>{setting.name}</b><small>{kindLabel(setting.kind)}</small></span>
                <span className={approved ? "status success" : pending ? "status warning" : "status"}>
                  {approved ? `${approved} 个正式版本` : pending ? "候选待确认" : "尚未定妆"}
                </span>
              </button>
            );
          })}
          {!settingsLoading && visibleSettings.length === 0 ? (
            <div className="empty compact">
              {settings.length === 0
                ? "暂无可用设定卡，请先在创作资料中创建角色、地点或道具。"
                : "没有符合当前搜索条件的设定卡。"}
            </div>
          ) : null}
        </div>
      </section>

      <section className="visual-canon-library">
        <header>
          <div><strong>{selectedSetting?.name ?? "视觉设定"}</strong><span>{selectedSetting?.summary || "选择左侧设定卡"}</span></div>
          <span className="status">候选需人工确认</span>
        </header>
        {error ? <div className="notice notice-danger" role="alert">{error}</div> : null}
        <div className="visual-canon-guidance">
          图片负责稳定身份与造型。优先使用中性表情、自然姿态和可读清空间关系的参考图；避免强动作、极端透视和戏剧性彩光。
        </div>
        <div className="visual-canon-slots">
          {selectedCanons.map((canon) => (
            <CanonSlot key={canon.id} canon={canon} working={working} onApprove={approveCanon} />
          ))}
          {selectedCanons.length === 0 ? <div className="empty compact">当前设定还没有视觉版本，可以从下方上传第一张候选图。</div> : null}
        </div>
        {selectedSetting ? (
          <div className="visual-upload-form">
            <h3>上传新候选</h3>
            <div className="visual-upload-row">
              <label>职责
                <select className="select" value={duty} onChange={(event) => {
                  const next = event.target.value as VisualCanon["duty"];
                  setDuty(next);
                  setLabel(defaultLabel(next));
                }}>
                  {selectedSetting.kind === "character" ? <><option value="identity">角色身份</option><option value="costume">服装变体</option></> : null}
                  {selectedSetting.kind === "location" ? <option value="scene">场景主视图</option> : null}
                  {selectedSetting.kind === "item" ? <option value="prop">道具造型</option> : null}
                </select>
              </label>
              <label>变体标识<input className="input" value={variantKey} onChange={(event) => setVariantKey(event.target.value.toLowerCase().replace(/[^a-z0-9_-]/g, ""))} /></label>
              <label>显示名称<input className="input" value={label} maxLength={120} onChange={(event) => setLabel(event.target.value)} /></label>
            </div>
            <div className="visual-upload-row">
              <label>必须保留<input className="input" value={includeFeatures} placeholder="高马尾，左眉疤痕（逗号分隔）" onChange={(event) => setIncludeFeatures(event.target.value)} /></label>
              <label>必须避免<input className="input" value={excludeFeatures} placeholder="强笑，霓虹彩光（逗号分隔）" onChange={(event) => setExcludeFeatures(event.target.value)} /></label>
              <label>默认参考强度 <b>{defaultStrength}</b><input type="range" min={1} max={100} value={defaultStrength} onChange={(event) => setDefaultStrength(Number(event.target.value))} /></label>
            </div>
            <div className="visual-upload-actions">
              <input type="file" accept="image/jpeg,image/png,image/webp" onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
              <label className="visual-rights"><input type="checkbox" checked={rightsConfirmed} onChange={(event) => setRightsConfirmed(event.target.checked)} />我确认拥有这张图片的使用权</label>
              <button className="button secondary" type="button" disabled={working !== null || !file || !label.trim() || !variantKey} onClick={() => void uploadCandidate()}>
                {working === "upload" ? "上传中..." : "上传为候选"}
              </button>
            </div>
          </div>
        ) : null}
      </section>

      <section className="visual-shot-bindings">
        <header><strong>逐镜参考</strong><span>绑定精确版本</span></header>
        <select className="select" value={selectedShot?.shotKey ?? ""} onChange={(event) => onSelectShot(event.target.value)}>
          {formalShots.map((shot) => <option key={shot.id} value={shot.shotKey}>{shot.shotKey} · {shot.title}</option>)}
        </select>
        {selectedShot ? (
          <>
            <div className="visual-shot-summary"><b>{selectedShot.storyFunction}</b><span>{selectedShot.visualIntent}</span></div>
            <div className="visual-reference-actions">
              <button className="button ghost" type="button" onClick={() => setSelections(recommendedVisualReferences(canons, shotContext))}>采用推荐</button>
              <button className="button primary" type="button" disabled={working !== null} onClick={() => void saveReferences()}>{working === "references" ? "保存中..." : "保存本镜参考"}</button>
            </div>
            {referenceWarnings.length ? <div className="notice notice-warning">{referenceWarnings.join("；")}</div> : null}
            <div className="visual-reference-options">
              {referenceOptions.map(({ canon, version, historical }) => {
                const selected = selections.find((item) => item.canonVersionId === version.id);
                return (
                  <div className={selected ? "visual-reference-option selected" : "visual-reference-option"} key={version.id}>
                    <label>
                      <input type="checkbox" checked={Boolean(selected)} onChange={(event) => setSelections((current) => event.target.checked
                        ? [...current, { canonVersionId: version.id, strength: version.defaultStrength }]
                        : current.filter((item) => item.canonVersionId !== version.id))} />
                      <img src={assetPreviewUrl(version.asset.id)} alt="" />
                      <span><b>{version.settingName}</b><small>{dutyLabel(canon.duty)} · {version.label} · v{version.versionNo}{historical ? " · 本镜历史绑定" : ""}</small></span>
                    </label>
                    {selected ? <label className="visual-strength">强度 {selected.strength}<input type="range" min={1} max={100} value={selected.strength} onChange={(event) => setSelections((current) => current.map((item) => item.canonVersionId === version.id ? { ...item, strength: Number(event.target.value) } : item))} /></label> : null}
                  </div>
                );
              })}
              {referenceOptions.length === 0 ? <div className="empty compact">先在中栏批准至少一个视觉设定版本。</div> : null}
            </div>
          </>
        ) : null}
      </section>
    </div>
  );
}

function CanonSlot({ canon, working, onApprove }: { canon: VisualCanon; working: string | null; onApprove: (canon: VisualCanon) => Promise<void> }) {
  const current = currentCanonVersion(canon);
  return (
    <article className="visual-canon-slot">
      <div className="visual-canon-slot-title">
        <div><strong>{dutyLabel(canon.duty)} · {canon.label}</strong><span>{canon.variantKey}</span></div>
        <span className={canon.candidateAsset ? "status warning" : current ? "status success" : "status"}>{canon.candidateAsset ? "候选待确认" : current ? `正式 v${current.versionNo}` : "无正式版本"}</span>
      </div>
      <div className="visual-canon-images">
        {current ? <figure><img src={assetPreviewUrl(current.asset.id)} alt={`${current.settingName}${current.label}正式版本`} /><figcaption>{current.label} · 正式 v{current.versionNo}</figcaption></figure> : null}
        {canon.candidateAsset ? <figure className="candidate"><img src={assetPreviewUrl(canon.candidateAsset.id)} alt={`${canon.settingName}${canon.label}候选`} /><figcaption>新候选</figcaption></figure> : null}
      </div>
      {canon.candidateAsset ? (
        <div className="visual-canon-confirm">
          <span>保留：{canon.candidateIncludeFeatures.join("、") || "未指定"}</span>
          <span>避免：{canon.candidateExcludeFeatures.join("、") || "未指定"}</span>
          <button className="button primary" type="button" disabled={working !== null} onClick={() => void onApprove(canon)}>{working === `approve:${canon.id}` ? "确认中..." : "确认为视觉设定"}</button>
        </div>
      ) : null}
      {canon.versions.length > 1 ? <small className="visual-history">保留 {canon.versions.length} 个不可变历史版本</small> : null}
    </article>
  );
}

function characterSetting(value: CharacterSetting): SettingCard {
  return { id: value.id, kind: "character", name: value.name, summary: value.appearance || value.identity || "角色设定" };
}

function locationSetting(value: LocationSetting): SettingCard {
  return { id: value.id, kind: "location", name: value.name, summary: value.description || value.type || "地点设定" };
}

function itemSetting(value: ItemSetting): SettingCard {
  return { id: value.id, kind: "item", name: value.name, summary: value.description || value.type || "道具设定" };
}

function settingKey(value: SettingCard | undefined): string | null {
  return value ? `${value.kind}:${value.id}` : null;
}

function kindLabel(kind: SettingKind): string {
  return { character: "角色", location: "地点", item: "道具" }[kind];
}

function defaultLabel(duty: VisualCanon["duty"]): string {
  return { identity: "标准身份", costume: "常服", scene: "场景主视图", prop: "标准造型" }[duty];
}

function splitFeatures(value: string): string[] {
  return Array.from(new Set(value.split(/[，,]/).map((item) => item.trim()).filter(Boolean)));
}

function buildReferenceOptions(
  canons: VisualCanon[],
  references: ShotVisualReferenceSet["references"],
): Array<{ canon: VisualCanon; version: VisualCanonVersion; historical: boolean }> {
  const options: Array<{ canon: VisualCanon; version: VisualCanonVersion; historical: boolean }> = [];
  const seen = new Set<string>();
  for (const canon of canons) {
    const version = currentCanonVersion(canon);
    if (!version) continue;
    options.push({ canon, version, historical: false });
    seen.add(version.id);
  }
  for (const reference of references) {
    if (seen.has(reference.canonVersionId)) continue;
    const canon = canons.find((item) => item.versions.some((version) => version.id === reference.canonVersionId));
    const version = canon?.versions.find((item) => item.id === reference.canonVersionId);
    if (canon && version) {
      options.push({ canon, version, historical: true });
      seen.add(version.id);
    }
  }
  return options;
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}
