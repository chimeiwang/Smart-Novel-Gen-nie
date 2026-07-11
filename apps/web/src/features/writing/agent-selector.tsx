"use client";

import { useState } from "react";

import {
  type AgentId,
  AGENT_REGISTRY,
  getOptionalAgents,
  getRequiredAgents,
} from "@/features/writing/agent-registry";

type AgentSelectorProps = {
  selectedAgents: AgentId[];
  onChange: (agents: AgentId[]) => void;
  targetWordCount: number;
  onWordCountChange: (count: number) => void;
  disabled?: boolean;
};

// Agent 信息
const AGENT_INFO: Record<string, { tone: string; emoji: string }> = {
  host: { tone: "blue", emoji: "控" },
  writer: { tone: "purple", emoji: "写" },
  validator: { tone: "green", emoji: "验" },
  plotAnalyzer: { tone: "orange", emoji: "剧" },
  characterAdvisor: { tone: "pink", emoji: "角" },
  styleMimic: { tone: "cyan", emoji: "风" },
  sceneDesigner: { tone: "blue", emoji: "景" },
  foreshadowing: { tone: "yellow", emoji: "伏" },
  recorder: { tone: "gray", emoji: "记" },
};

/**
 * Agent 选择面板（可折叠）
 */
export function AgentSelector({
  selectedAgents,
  onChange,
  targetWordCount,
  onWordCountChange,
  disabled,
}: AgentSelectorProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const requiredAgents = getRequiredAgents();
  const optionalAgents = getOptionalAgents();

  const toggleAgent = (agentId: AgentId) => {
    if (disabled) return;
    if (requiredAgents.some((a) => a.id === agentId)) return;

    if (selectedAgents.includes(agentId)) {
      onChange(selectedAgents.filter((id) => id !== agentId));
    } else {
      onChange([...selectedAgents, agentId]);
    }
  };

  const selectedOptionalCount = selectedAgents.filter(
    id => optionalAgents.some(a => a.id === id)
  ).length;

  return (
    <div className="agent-selector-wrapper">
      {/* 折叠头部 */}
      <button
        className="header"
        onClick={() => setIsExpanded(!isExpanded)}
        type="button"
      >
        <div className="header-info">
          <span className="header-icon">⚙️</span>
          <span className="header-text">写作配置</span>
          <span className="header-summary">
            {targetWordCount}字 · {selectedAgents.length} 位助手
          </span>
        </div>
        <span className={`header-arrow ${isExpanded ? "open" : ""}`}>▼</span>
      </button>

      {/* 展开内容 */}
      {isExpanded && (
        <div className="body">
          {/* 目标字数 */}
          <div className="section">
            <div className="section-label">目标字数</div>
            <div className="word-slider">
              <input
                type="range"
                min={500}
                max={20000}
                step={500}
                value={targetWordCount}
                onChange={(e) => onWordCountChange(parseInt(e.target.value))}
                disabled={disabled}
              />
              <span className="word-value">{targetWordCount}</span>
              <span className="word-unit">字</span>
            </div>
          </div>

          {/* 必选助手 */}
          <div className="section">
            <div className="section-label">必选助手</div>
            <div className="agent-grid">
              {requiredAgents.map((agent) => {
                const info = AGENT_INFO[agent.id];
                return (
                  <div key={agent.id} className="agent-chip required">
                    <span className={`chip-emoji tone-${info?.tone ?? "blue"}`}>{info?.emoji}</span>
                    <span className="chip-name">{agent.name}</span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* 可选助手 */}
          <div className="section">
            <div className="section-label">
              可选助手
              <span className="label-count">已选 {selectedOptionalCount}</span>
            </div>
            <div className="agent-grid">
              {optionalAgents.map((agent) => {
                const info = AGENT_INFO[agent.id];
                const isSelected = selectedAgents.includes(agent.id);
                return (
                  <button
                    key={agent.id}
                    className={`agent-chip selectable ${isSelected ? "selected" : ""}`}
                    onClick={() => toggleAgent(agent.id)}
                    disabled={disabled}
                    type="button"
                  >
                    <span className={`chip-emoji tone-${info?.tone ?? "blue"}`}>{info?.emoji}</span>
                    <span className="chip-name">{agent.name}</span>
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export function getDefaultSelectedAgents(): AgentId[] {
  return [];
}
