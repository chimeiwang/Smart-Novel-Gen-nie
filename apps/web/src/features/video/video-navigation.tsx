import { videoSceneStatusLabel } from "./video-workspace-helpers";
import { VIDEO_STAGES, type VideoStage } from "./video-workspace-state";
import type { VideoProject, VideoScene } from "./video-workspace-types";

type VideoNavigationProps = {
  projects: VideoProject[];
  activeProjectId: string | null;
  scenes: VideoScene[];
  activeSceneId: string | null;
  stage: VideoStage;
  working: string | null;
  onCreateProject: () => void;
  onSelectProject: (projectId: string) => void;
  onSelectScene: (sceneId: string) => void;
  onSelectStage: (stage: VideoStage) => void;
};

// 左栏只负责项目、场景与阶段定位，具体业务动作统一交回工作台容器。
export function VideoNavigation({
  projects,
  activeProjectId,
  scenes,
  activeSceneId,
  stage,
  working,
  onCreateProject,
  onSelectProject,
  onSelectScene,
  onSelectStage,
}: VideoNavigationProps) {
  return (
    <aside className="panel video-navigation-panel">
      <div className="panel-header">
        <div>
          <h2 className="title-md">视频试制</h2>
          <span className="status-text">长篇开发预览</span>
        </div>
        <button className="button secondary" type="button" onClick={onCreateProject}>
          {working === "project" ? "创建中..." : "新建"}
        </button>
      </div>
      <div className="panel-body video-navigation-body">
        <div className="video-navigation-group">
          <span className="video-navigation-label">项目</span>
          {projects.length === 0 ? <span className="status-text">尚无项目</span> : null}
          {projects.map((project) => (
            <button
              className={`video-navigation-item ${project.id === activeProjectId ? "active" : ""}`}
              key={project.id}
              type="button"
              onClick={() => onSelectProject(project.id)}
            >
              <strong>{project.title}</strong>
              <span>{project.sceneCount} 个试制场景</span>
            </button>
          ))}
        </div>
        {activeProjectId ? (
          <div className="video-navigation-group">
            <span className="video-navigation-label">试制场景</span>
            {scenes.length === 0 ? <span className="status-text">等待冻结原文事件</span> : null}
            {scenes.map((scene) => (
              <button
                className={`video-navigation-item ${scene.id === activeSceneId ? "active" : ""}`}
                key={scene.id}
                type="button"
                onClick={() => onSelectScene(scene.id)}
              >
                <strong>#{scene.ordinal} {scene.title}</strong>
                <span>{videoSceneStatusLabel(scene.status)} · {scene.durationSeconds}s</span>
              </button>
            ))}
          </div>
        ) : null}
        <div className="video-navigation-group">
          <span className="video-navigation-label">五个任务</span>
          {VIDEO_STAGES.map((item, index) => (
            <button
              className={`video-stage-navigation-item ${item.value === stage ? "active" : ""}`}
              key={item.value}
              type="button"
              onClick={() => onSelectStage(item.value)}
            >
              <span>{index + 1}</span>
              {item.label}
            </button>
          ))}
        </div>
      </div>
    </aside>
  );
}
