"use client";

import type { Character, ScriptDocument, ScriptLine, ScriptScene } from "./types";
import { duplicateScene, nodeIdentity, removeScene, reorderScene } from "./script-document-state";
import { countTextLength } from "@/shared/lib/word-count";

const newKey = () => `node_${crypto.randomUUID().replaceAll("-", "")}`;

export function EpisodeScriptEditor({ document, characters, disabled, selectedSceneIds, onSelectedSceneIds, onChange }: {
  document: ScriptDocument;
  characters: Character[];
  disabled: boolean;
  selectedSceneIds: string[];
  onSelectedSceneIds: (ids: string[]) => void;
  onChange: (document: ScriptDocument) => void;
}) {
  const scenes = document.scenes ?? [];
  const updateScene = (key: string, update: Partial<ScriptScene>) => onChange({ ...document, scenes: scenes.map((scene) => nodeIdentity(scene) === key ? { ...scene, ...update } : scene) });
  const updateLine = (scene: ScriptScene, lineKey: string, update: Partial<ScriptLine>) => updateScene(nodeIdentity(scene), { lines: (scene.lines ?? []).map((line) => nodeIdentity(line) === lineKey ? { ...line, ...update } : line) });
  const appendLine = (scene: ScriptScene, kind: ScriptLine["kind"]) => updateScene(nodeIdentity(scene), { lines: [...(scene.lines ?? []), { tempKey: newKey(), kind, text: "", sourceRefs: [], speakerId: kind === "dialogue" ? characters[0]?.id ?? null : null }] });
  return <div className="episode-script-editor">
    <fieldset disabled={disabled} className="episode-fieldset">
      <div className="episode-overview">
        <label>本集讲什么<textarea className="textarea" value={document.overview?.summary ?? ""} maxLength={4000} rows={3} placeholder="这集的冲突、转折和结尾" onChange={(event) => onChange({ ...document, overview: { ...{ summary: "", creativeIntent: "" }, ...document.overview, summary: event.target.value } })} /></label>
        <label>改编意图<textarea className="textarea" value={document.overview?.creativeIntent ?? ""} maxLength={4000} rows={2} placeholder="例如：保留林岚对顾舟的不信任，雨夜氛围压抑" onChange={(event) => onChange({ ...document, overview: { ...{ summary: "", creativeIntent: "" }, ...document.overview, creativeIntent: event.target.value } })} /></label>
        <label>目标时长（秒，可留空）<input className="input" type="number" min={1} max={86400} value={document.overview?.targetDurationSeconds ?? ""} onChange={(event) => onChange({ ...document, overview: { ...{ summary: "", creativeIntent: "" }, ...document.overview, targetDurationSeconds: event.target.value ? Number(event.target.value) : null } })} /></label>
      </div>
      {scenes.map((scene, index) => {
        const key = nodeIdentity(scene);
        return <section className="episode-scene" key={key}>
          <header className="episode-toolbar"><label className="episode-scene-selection"><input type="checkbox" checked={Boolean(scene.id && selectedSceneIds.includes(scene.id))} disabled={disabled || !scene.id} onChange={(event) => { if (!scene.id) return; onSelectedSceneIds(event.target.checked ? [...selectedSceneIds, scene.id] : selectedSceneIds.filter((id) => id !== scene.id)); }} />第 {index + 1} 场</label><input className="input" aria-label={`第${index + 1}场标题`} value={scene.title} maxLength={160} placeholder="场次标题" onChange={(event) => updateScene(key, { title: event.target.value })} /><div className="episode-inline-actions"><button className="button ghost sm" type="button" disabled={index === 0} onClick={() => onChange(reorderScene(document, key, -1))}>上移</button><button className="button ghost sm" type="button" disabled={index === scenes.length - 1} onClick={() => onChange(reorderScene(document, key, 1))}>下移</button><button className="button ghost sm" type="button" onClick={() => onChange({ ...document, scenes: [...scenes.slice(0, index + 1), duplicateScene(scene, newKey), ...scenes.slice(index + 1)] })}>复制</button><button className="button ghost sm" type="button" onClick={() => { if (window.confirm("删除这场在工作稿中的内容及其承接关联？已确认历史版本会保留。")) onChange(removeScene(document, key)); }}>删除</button></div></header>
          <div className="episode-scene-meta"><label>地点<input className="input" value={scene.locationLabel} maxLength={240} placeholder="顾舟住所外" onChange={(event) => updateScene(key, { locationLabel: event.target.value })} /></label><label>昼夜 / 天气<input className="input" value={scene.timeLabel} maxLength={160} placeholder="雨夜" onChange={(event) => updateScene(key, { timeLabel: event.target.value })} /></label><label>剧情时间<input className="input" value={scene.narrativeTime} maxLength={400} placeholder="当晚 / 三日前的回忆" onChange={(event) => updateScene(key, { narrativeTime: event.target.value })} /></label></div>
          <div className="episode-character-selection"><span className="muted">出场角色</span>{characters.map((character) => <label key={character.id}><input type="checkbox" checked={(scene.characterIds ?? []).includes(character.id)} onChange={(event) => updateScene(key, { characterIds: event.target.checked ? [...(scene.characterIds ?? []), character.id] : (scene.characterIds ?? []).filter((id) => id !== character.id) })} />{character.name}</label>)}</div>
          {(scene.lines ?? []).map((line) => <div className="episode-script-line" key={nodeIdentity(line)}><div className="episode-toolbar"><span className="badge">{line.kind === "dialogue" ? "对白" : line.kind === "narration" ? "旁白" : "行动"}</span>{line.kind === "dialogue" ? <select className="select" aria-label="对白角色" value={line.speakerId ?? ""} onChange={(event) => updateLine(scene, nodeIdentity(line), { speakerId: event.target.value })}>{characters.map((character) => <option value={character.id} key={character.id}>{character.name}</option>)}</select> : null}<span className="muted">{countTextLength(line.text)} 字{line.sourceRefs?.length ? ` · ${line.sourceRefs.length} 处原文依据` : ""}</span><button className="button ghost sm" type="button" onClick={() => onChange({ ...document, scenes: scenes.map((item) => nodeIdentity(item) === key ? { ...item, lines: (item.lines ?? []).filter((candidate) => nodeIdentity(candidate) !== nodeIdentity(line)) } : item), dependencies: (document.dependencies ?? []).filter((dependency) => dependency.consumerLineId !== nodeIdentity(line)) })}>删除段落</button></div><textarea className="textarea" aria-label={`${scene.title || `第${index + 1}场`}${line.kind === "dialogue" ? "对白" : "内容"}`} value={line.text} maxLength={8000} rows={Math.max(2, Math.min(8, line.text.split("\n").length + 1))} onChange={(event) => updateLine(scene, nodeIdentity(line), { text: event.target.value })} /></div>)}
          <div className="episode-inline-actions"><button className="button ghost sm" type="button" onClick={() => appendLine(scene, "action")}>＋行动</button><button className="button ghost sm" type="button" disabled={!characters.length} onClick={() => appendLine(scene, "dialogue")}>＋对白</button><button className="button ghost sm" type="button" onClick={() => appendLine(scene, "narration")}>＋旁白</button></div>
        </section>;
      })}
      <button className="button" type="button" disabled={scenes.length >= 60} onClick={() => onChange({ ...document, scenes: [...scenes, { tempKey: newKey(), title: "", locationLabel: "", timeLabel: "", narrativeTime: "", characterIds: [], lines: [] }] })}>＋添加一场戏</button>
    </fieldset>
  </div>;
}
