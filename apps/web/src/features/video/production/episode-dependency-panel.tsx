"use client";

import { useEffect, useState } from "react";
import { browserApi } from "@/lib/api/browser";
import { requireApiData } from "@/lib/api/response";
import { nodeIdentity } from "./script-document-state";
import type { Episode, ScriptDocument, ScriptVersion } from "./types";

export function EpisodeDependencyPanel({ episodeId, episodes, document, disabled, onChange }: { episodeId: string; episodes: Episode[]; document: ScriptDocument; disabled: boolean; onChange: (document: ScriptDocument) => void }) {
  const [producerId, setProducerId] = useState("");
  const [versions, setVersions] = useState<ScriptVersion[]>([]);
  const [versionId, setVersionId] = useState("");
  const [stateKey, setStateKey] = useState("");
  const [sceneId, setSceneId] = useState("");
  const [narrativeTime, setNarrativeTime] = useState("");
  const [description, setDescription] = useState("");
  const [endingDescription, setEndingDescription] = useState("");
  const [endingTime, setEndingTime] = useState("");
  const [error, setError] = useState<string | null>(null);
  const version = versions.find((item) => item.id === versionId);
  const state = version?.document.endingStates?.find((item) => item.key === stateKey);

  useEffect(() => {
    if (!producerId) return;
    const controller = new AbortController();
    void browserApi.GET("/api/v1/video/episodes/{episode_id}/script/versions", { params: { path: { episode_id: producerId } }, signal: controller.signal }).then(requireApiData).then((result) => { if (!controller.signal.aborted) setVersions(result.versions); }).catch((failure) => { if (!controller.signal.aborted) setError(failure instanceof Error ? failure.message : "读取承接版本失败"); });
    return () => controller.abort();
  }, [producerId]);

  return <section className="episode-dependency-panel"><h3>本集状态与承接</h3><p className="muted">承接必须选择一份正式剧本的确切状态。回忆、并行场景分别说明剧情时间，不按集号自动继承。</p><fieldset disabled={disabled} className="episode-fieldset">
    <h4>本集结束时留下什么</h4>{(document.endingStates ?? []).map((ending) => <article className="episode-ending-state" key={ending.key}><label>状态描述<textarea className="textarea" rows={2} value={ending.description} maxLength={2000} onChange={(event) => onChange({ ...document, endingStates: (document.endingStates ?? []).map((item) => item.key === ending.key ? { ...item, description: event.target.value } : item) })} /></label><label>剧情时间<input className="input" value={ending.narrativeTime ?? ""} maxLength={400} onChange={(event) => onChange({ ...document, endingStates: (document.endingStates ?? []).map((item) => item.key === ending.key ? { ...item, narrativeTime: event.target.value } : item) })} /></label><button className="button ghost sm" type="button" onClick={() => onChange({ ...document, endingStates: (document.endingStates ?? []).filter((item) => item.key !== ending.key) })}>移除此状态</button></article>)}
    <label>新增结尾状态<input className="input" value={endingDescription} maxLength={2000} placeholder="例如：林岚将信交给顾舟，顾舟尚未开信" onChange={(event) => setEndingDescription(event.target.value)} /></label><label>状态发生时间<input className="input" value={endingTime} maxLength={400} placeholder="雨夜，送信之后" onChange={(event) => setEndingTime(event.target.value)} /></label><button className="button" type="button" disabled={!endingDescription.trim()} onClick={() => { onChange({ ...document, endingStates: [...(document.endingStates ?? []), { key: `state_${crypto.randomUUID().replaceAll("-", "")}`, description: endingDescription.trim(), narrativeTime: endingTime, entityIds: [] }] }); setEndingDescription(""); setEndingTime(""); }}>添加状态</button>
    <h4>本集引用了哪些已确认事实</h4>{(document.dependencies ?? []).map((dependency, index) => <article className="episode-ending-state" key={`${dependency.producerScriptVersionId}:${dependency.producerStateKey}:${index}`}><strong>{episodes.find((item) => item.id === dependency.producerEpisodeId)?.title ?? "来源集"}</strong><p>{dependency.description}</p><p className="muted">剧情时间：{dependency.narrativeTime} · 使用正式版本 {dependency.producerScriptVersionId}</p><p className="muted">作用于：{document.scenes?.find((item) => nodeIdentity(item) === dependency.consumerSceneId)?.title ?? "本集场次"}</p><button className="button ghost sm" type="button" onClick={() => onChange({ ...document, dependencies: (document.dependencies ?? []).filter((_, itemIndex) => itemIndex !== index) })}>移除承接</button></article>)}
    <details><summary>明确添加承接依据</summary>{error ? <p className="notice notice-danger" role="alert">{error}</p> : null}<label>来源集<select className="select" value={producerId} onChange={(event) => { setProducerId(event.target.value); setVersions([]); setVersionId(""); setStateKey(""); setError(null); }}><option value="">选择已确认的集</option>{episodes.filter((item) => item.id !== episodeId && item.currentScriptVersionId).map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}</select></label><label>正式剧本版本<select className="select" value={versionId} onChange={(event) => { setVersionId(event.target.value); setStateKey(""); }}><option value="">选择确切版本</option>{versions.map((item) => <option key={item.id} value={item.id}>正式剧本 v{item.versionNo}</option>)}</select></label><label>承接状态<select className="select" value={stateKey} onChange={(event) => setStateKey(event.target.value)}><option value="">选择该版本的结尾状态</option>{(version?.document.endingStates ?? []).map((item) => <option key={item.key} value={item.key}>{item.description}</option>)}</select></label>{state ? <p className="muted">来源剧情时间：{state.narrativeTime || "作者未填写"}</p> : null}<label>作用于本集哪场戏<select className="select" value={sceneId} onChange={(event) => setSceneId(event.target.value)}><option value="">选择本集场次</option>{(document.scenes ?? []).map((scene, index) => <option key={nodeIdentity(scene)} value={nodeIdentity(scene)}>第 {index + 1} 场 · {scene.title}</option>)}</select></label><label>本场与来源的时间关系<input className="input" value={narrativeTime} maxLength={400} placeholder="例如：交信之后；或三日前回忆，只引用当时状态" onChange={(event) => setNarrativeTime(event.target.value)} /></label><label>本场怎样依赖这个状态<textarea className="textarea" rows={2} value={description} maxLength={2000} placeholder="顾舟要开信，因此必须先持有这封信" onChange={(event) => setDescription(event.target.value)} /></label><button className="button" type="button" disabled={!producerId || !version || !state || !sceneId || !narrativeTime.trim() || !description.trim()} onClick={() => { if (!version || !state) return; onChange({ ...document, dependencies: [...(document.dependencies ?? []), { producerEpisodeId: producerId, producerScriptVersionId: version.id, producerStateKey: state.key, consumerSceneId: sceneId, consumerLineId: null, narrativeTime: narrativeTime.trim(), description: description.trim() }] }); setDescription(""); }}>添加这条承接</button></details>
  </fieldset></section>;
}
