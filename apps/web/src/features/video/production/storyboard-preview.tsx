import type { ScriptVersion, StoryboardDocument } from "./types";

export function StoryboardPreview({ document, scriptVersion }: { document: StoryboardDocument; scriptVersion: ScriptVersion | null }) {
  const scenes = new Map((scriptVersion?.document.scenes ?? []).flatMap((scene) => scene.id ? [[scene.id, scene]] : []));
  return <div className="episode-storyboard-preview">{(document.shots ?? []).map((shot, index) => {
    const scene = scenes.get(shot.scriptSceneId);
    return <article key={shot.id ?? shot.tempKey ?? index}>
      <header><span>{String(index + 1).padStart(2, "0")}</span><div><strong>{shot.title}</strong><small>{scene?.title ?? shot.scriptSceneId} · {shot.durationMs / 1000} 秒</small></div></header>
      <p>{shot.action}</p>
      <dl><div><dt>生成依据</dt><dd>{shot.productionIntent.provider} · {shot.productionIntent.model} · {shot.productionIntent.executionMode === "simulated" ? "隔离模拟" : "真实执行"}</dd></div><div><dt>规格</dt><dd>{shot.productionIntent.ratio} · {shot.productionIntent.resolution} · {shot.productionIntent.outputFormat} · {shot.productionIntent.references.length} 份视觉参考</dd></div><div><dt>提示词</dt><dd>{shot.productionIntent.prompt}</dd></div></dl>
    </article>;
  })}{!(document.shots?.length) ? <div className="empty">这份分镜没有镜头。</div> : null}</div>;
}
