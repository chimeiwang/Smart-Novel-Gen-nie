"use client";

import { useEffect, useMemo, useState } from "react";

import { episodeTakeContentUrl, getProductionBaseline, getTakeAdoption, listTakeCandidates } from "./production-api";
import {
  takeCandidateMatchesSource,
  takeDirectInputDifferences,
  takeReferenceHashesForReview,
} from "./take-adoption-state";
import type {
  CreateTakeAdoptionRequest,
  ProductionBaseline,
  StoryboardVersion,
  TakeAdoption,
  TakeCandidate,
  TakeCandidateList,
} from "./types";

type Props = {
  episodeId: string;
  storyboard: StoryboardVersion;
  currentBaseline: ProductionBaseline | null;
  selectedAdoptionIds: Readonly<Record<string, string>>;
  enabled: boolean;
  busy: boolean;
  onCreateAdoption: (
    candidate: TakeCandidate,
    comparison: CreateTakeAdoptionRequest["comparison"],
  ) => Promise<TakeAdoption>;
  onSelectAdoption: (shotVersionId: string, adoptionId: string | null) => void;
};

const errorText = (failure: unknown) => failure instanceof Error ? failure.message : "读取 Take 候选失败";
const shortHash = (value: string) => `${value.slice(0, 10)}…${value.slice(-8)}`;
const mediaSize = (bytes: number) => `${(bytes / 1024 / 1024).toFixed(1)} MB`;

export function TakeAdoptionReview({ episodeId, storyboard, currentBaseline, selectedAdoptionIds, enabled, busy, onCreateAdoption, onSelectAdoption }: Props) {
  const [targetShotVersionId, setTargetShotVersionId] = useState(storyboard.shots[0]?.id ?? "");
  const [page, setPage] = useState<TakeCandidateList | null>(null);
  const [selectedTakeId, setSelectedTakeId] = useState<string | null>(null);
  const [sourceBaseline, setSourceBaseline] = useState<ProductionBaseline | null>(null);
  const [existingAdoption, setExistingAdoption] = useState<TakeAdoption | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<{ scope: string; message: string } | null>(null);
  const [summary, setSummary] = useState("");
  const [reviewedInputs, setReviewedInputs] = useState(false);
  const [checkedHashes, setCheckedHashes] = useState<string[]>([]);

  const target = storyboard.shots.find((shot) => shot.id === targetShotVersionId) ?? storyboard.shots[0] ?? null;
  const visiblePage = page?.targetShotVersionId === targetShotVersionId ? page : null;
  const selectedTake = visiblePage?.takes.find((take) => take.id === selectedTakeId) ?? null;
  const visibleSourceBaseline = sourceBaseline?.id === selectedTake?.sourceBaselineId ? sourceBaseline : null;
  const visibleExistingAdoption = existingAdoption
    && existingAdoption.id === selectedTake?.adoptionId
    && existingAdoption.targetShotVersionId === target?.id
    && existingAdoption.sourceTakeId === selectedTake?.id
    && existingAdoption.sourceBaselineId === selectedTake?.sourceBaselineId
    ? existingAdoption
    : null;
  const sourceShot = selectedTake && visibleSourceBaseline
    ? visibleSourceBaseline.shots.find((shot) => shot.shotVersionId === selectedTake.sourceShotVersionId) ?? null
    : null;
  const sourceMatches = Boolean(selectedTake && visibleSourceBaseline && takeCandidateMatchesSource(selectedTake, visibleSourceBaseline, sourceShot));
  const differences = sourceShot && target ? takeDirectInputDifferences(sourceShot, target) : [];
  const referenceHashes = sourceShot ? takeReferenceHashesForReview(sourceShot) : [];
  const allReferenceHashesChecked = referenceHashes.every((hash) => checkedHashes.includes(hash));
  const selectedCount = useMemo(() => storyboard.shots.filter((shot) => Boolean(selectedAdoptionIds[shot.id])).length, [selectedAdoptionIds, storyboard.shots]);

  useEffect(() => {
    let alive = true;
    if (!targetShotVersionId) return () => { alive = false; };
    void listTakeCandidates(episodeId, targetShotVersionId).then((value) => {
      if (!alive) return;
      setPage(value);
      setError(null);
    }).catch((failure) => { if (alive) setError({ scope: targetShotVersionId, message: errorText(failure) }); });
    return () => { alive = false; };
  }, [episodeId, targetShotVersionId]);

  const selectedSourceBaselineId = selectedTake?.sourceBaselineId;
  const selectedAdoptionId = selectedTake?.adoptionId;
  useEffect(() => {
    let alive = true;
    if (!selectedSourceBaselineId) return () => { alive = false; };
    const requests = [
      getProductionBaseline(episodeId, selectedSourceBaselineId),
      selectedAdoptionId ? getTakeAdoption(episodeId, selectedAdoptionId) : Promise.resolve(null),
    ] as const;
    void Promise.all(requests).then(([baseline, adoption]) => {
      if (!alive) return;
      setSourceBaseline(baseline);
      setExistingAdoption(adoption);
      setError(null);
    }).catch((failure) => { if (alive) setError({ scope: selectedTakeId ?? "take", message: errorText(failure) }); });
    return () => { alive = false; };
  }, [episodeId, selectedAdoptionId, selectedSourceBaselineId, selectedTakeId]);

  const chooseTake = (takeId: string) => {
    setSelectedTakeId(takeId);
    setExistingAdoption(null);
    setReviewedInputs(false);
    setCheckedHashes([]);
    setSummary("");
    setError(null);
  };

  const loadMore = () => {
    if (!visiblePage?.nextBeforeTakeId || !targetShotVersionId || loadingMore) return;
    setLoadingMore(true);
    setError(null);
    void listTakeCandidates(episodeId, targetShotVersionId, visiblePage.nextBeforeTakeId).then((next) => {
      setPage((current) => current?.targetShotVersionId === targetShotVersionId && next.targetShotVersionId === targetShotVersionId ? {
        ...next,
        takes: [...current.takes, ...next.takes.filter((take) => !current.takes.some((old) => old.id === take.id))],
      } : current);
    }).catch((failure) => setError({ scope: targetShotVersionId, message: errorText(failure) })).finally(() => setLoadingMore(false));
  };

  const createAdoption = async () => {
    if (!selectedTake || !target || !sourceMatches || !reviewedInputs || !allReferenceHashesChecked || !summary.trim()) return;
    setError(null);
    try {
      const adoption = await onCreateAdoption(selectedTake, {
        sourceBaselineId: selectedTake.sourceBaselineId,
        targetShotVersionId: target.id,
        directInputsUnchanged: differences.length === 0,
        referenceHashesChecked: checkedHashes,
        summary: summary.trim(),
      });
      onSelectAdoption(target.id, adoption.id);
      setExistingAdoption(adoption);
      setPage((current) => current ? {
        ...current,
        takes: current.takes.map((take) => take.id === selectedTake.id ? { ...take, adopted: true, adoptionId: adoption.id } : take),
      } : current);
    } catch (failure) {
      setError({ scope: selectedTake.id, message: errorText(failure) });
    }
  };

  return <section className="episode-take-adoption-review">
    <header><div><h4>选择本次素材采用</h4><p>逐镜查找同集已归档 Take，核对冻结输入后创建 Adoption。记录创建后仍要在本次基线中明确选用。</p></div><span className="status">{selectedCount}/{storyboard.shotCount} 镜已选</span></header>
    <label>目标正式镜头<select className="select" value={target?.id ?? ""} disabled={busy} onChange={(event) => { setTargetShotVersionId(event.target.value); setSelectedTakeId(null); setError(null); }}>{storyboard.shots.map((shot) => <option key={shot.id} value={shot.id}>镜头 {shot.ordinal} · {shot.content.title}</option>)}</select></label>
    {target && selectedAdoptionIds[target.id] ? <div className="notice"><strong>本镜已选择 Adoption</strong><p>{selectedAdoptionIds[target.id]}</p><button className="button ghost sm" type="button" disabled={busy} onClick={() => onSelectAdoption(target.id, null)}>本次基线改为待生产</button></div> : null}
    {!visiblePage && error?.scope !== targetShotVersionId ? <p>正在读取合法 Take 候选…</p> : null}
    {error ? <p className="notice notice-danger" role="alert">{error.message}</p> : null}
    {visiblePage && !visiblePage.takes.length ? <div className="episode-empty compact"><h4>本集还没有可采用的 Take</h4><p>先确认不带素材的 B0；后续生成成功只会形成候选，仍需回到这里人工采用并确认新基线。</p></div> : null}
    {visiblePage?.takes.length ? <div className="episode-take-candidate-list">{visiblePage.takes.map((take) => <button type="button" key={take.id} className={take.id === selectedTakeId ? "selected" : ""} onClick={() => chooseTake(take.id)}><span>Take {take.takeNo}</span><div><strong>{take.model}</strong><small>{(take.durationMs / 1000).toFixed(1)} 秒 · {mediaSize(take.byteSize)} · {take.width && take.height ? `${take.width}×${take.height}` : "实测尺寸缺失"}</small></div><em>{take.adopted ? "已有采用记录" : "待核对"}</em></button>)}</div> : null}
    {visiblePage?.nextBeforeTakeId ? <button className="button ghost sm" type="button" disabled={loadingMore} onClick={loadMore}>{loadingMore ? "读取中…" : "加载更早 Take"}</button> : null}
    {selectedTake ? <article className="episode-take-comparison">
      <video controls preload="metadata" src={episodeTakeContentUrl(episodeId, selectedTake.id)} />
      <header><div><strong>Take {selectedTake.takeNo} 输入核对</strong><small>源制作 v{visibleSourceBaseline?.versionNo ?? "?"} · 源镜头版本 {selectedTake.sourceShotVersionId}</small></div><span>{new Date(selectedTake.createdAt).toLocaleString("zh-CN")}</span></header>
      <dl><div><dt>媒体</dt><dd>{selectedTake.mimeType} · {(selectedTake.durationMs / 1000).toFixed(1)} 秒 · {mediaSize(selectedTake.byteSize)}</dd></div><div><dt>输入哈希</dt><dd title={selectedTake.inputHash}>{shortHash(selectedTake.inputHash)}</dd></div><div><dt>直接输入</dt><dd>{sourceShot ? differences.length ? `有差异：${differences.join("、")}` : "冻结字段一致" : "正在读取源基线…"}</dd></div></dl>
      {visibleSourceBaseline && !sourceMatches ? <p className="notice notice-danger">Take 摘要与源基线的镜头身份或输入哈希不一致，不能创建采用记录。</p> : null}
      {visibleExistingAdoption ? <section className="notice"><strong>已有采用记录</strong><p>{visibleExistingAdoption.comparison.summary}</p><button className="button" type="button" disabled={busy || !enabled || !target || !sourceMatches} onClick={() => target && onSelectAdoption(target.id, visibleExistingAdoption.id)}>在本次基线使用这条记录</button></section> : <>
        <label className="episode-baseline-ack"><input type="checkbox" disabled={busy || !sourceMatches} checked={reviewedInputs} onChange={(event) => setReviewedInputs(event.target.checked)} />我已逐项核对源输入与目标镜头。{differences.length ? "上述字段已有变化，我仍认为这段素材符合当前语境。" : "直接生成输入保持一致，但我仍已检查当前剧情语境。"}</label>
        <fieldset><legend>源参考素材哈希</legend>{referenceHashes.map((hash) => <label key={hash}><input type="checkbox" disabled={busy || !sourceMatches} checked={checkedHashes.includes(hash)} onChange={(event) => setCheckedHashes((current) => event.target.checked ? [...current, hash] : current.filter((value) => value !== hash))} /><span title={hash}>{shortHash(hash)}</span></label>)}{sourceShot && !referenceHashes.length ? <p className="notice notice-warning">源基线没有可核对的 SHA-256，采用记录不会声称已核对参考哈希。</p> : null}</fieldset>
        <label>采用依据<textarea className="textarea" rows={3} maxLength={4000} disabled={busy || !sourceMatches} value={summary} placeholder="说明人物状态、动作连续性、场景与当前镜头为何仍适用" onChange={(event) => setSummary(event.target.value)} /></label>
        <button className="button" type="button" disabled={busy || !enabled || !sourceMatches || !reviewedInputs || !allReferenceHashesChecked || !summary.trim()} onClick={() => void createAdoption()}>{busy ? "正在记录…" : "记录采用并加入本次基线"}</button>
      </>}
    </article> : null}
    {currentBaseline ? <p className="muted">当前制作 v{currentBaseline.versionNo} 保持不变；只有确认新基线后，上述选择才成为当前制作输入。</p> : null}
  </section>;
}

export function ProductionBaselineAdoptionStatus({ baseline }: { baseline: ProductionBaseline | null }) {
  const adopted = baseline?.shots.filter((shot) => shot.status === "adopted") ?? [];
  const pending = baseline?.shots.filter((shot) => shot.status === "pending") ?? [];
  return <section className="episode-production-side-card">
    <header><strong>素材采用</strong><span>{baseline ? `制作 v${baseline.versionNo}` : "尚无基线"}</span></header>
    {!baseline ? <p>确认首个制作基线后，每个镜头会有明确的待生产或已采用状态。</p> : <>
      <p>{adopted.length} 镜已绑定 Adoption，{pending.length} 镜待生产。生成成功不会自动变成采用。</p>
      <div className="episode-baseline-shot-state">{baseline.shots.map((shot) => <article key={shot.shotVersionId}><span>镜头 {shot.ordinal}</span><strong>{shot.status === "adopted" ? "已采用" : "待生产"}</strong><small>{shot.adoptionId ? `采用记录 ${shot.adoptionId}` : "没有采用记录"}</small></article>)}</div>
    </>}
  </section>;
}
