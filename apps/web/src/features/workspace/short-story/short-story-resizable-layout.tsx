"use client";

import type { ReactNode } from "react";
import { Children, useCallback, useEffect } from "react";
import {
  Group,
  type Layout,
  type LayoutChangedMeta,
  Panel,
  Separator,
  useGroupRef,
} from "react-resizable-panels";

import {
  readShortStoryPanelLayout,
  SHORT_STORY_PANEL_CONSTRAINTS,
  SHORT_STORY_PANEL_IDS,
  type ShortStoryPanelStorage,
  writeShortStoryPanelLayout,
} from "./short-story-panel-layout";

type ShortStoryResizableLayoutProps = {
  children: ReactNode;
  novelId: string;
};

export function ShortStoryResizableLayout({ children, novelId }: ShortStoryResizableLayoutProps) {
  const panels = Children.toArray(children);
  const groupRef = useGroupRef();

  const getStorage = useCallback((): ShortStoryPanelStorage | null => {
    try {
      return window.localStorage;
    } catch {
      return null;
    }
  }, []);

  useEffect(() => {
    const savedLayout = readShortStoryPanelLayout(getStorage(), novelId);
    if (savedLayout) groupRef.current?.setLayout(savedLayout);
  }, [getStorage, groupRef, novelId]);

  const saveLayout = useCallback((layout: Layout, meta: LayoutChangedMeta) => {
    if (!meta.isUserInteraction) return;
    writeShortStoryPanelLayout(getStorage(), novelId, layout);
  }, [getStorage, novelId]);

  return (
    <Group
      className="short-story-grid"
      groupRef={groupRef}
      id={`short-story-layout-${novelId}`}
      orientation="horizontal"
      onLayoutChanged={saveLayout}
      resizeTargetMinimumSize={{ coarse: 28, fine: 12 }}
    >
      <Panel
        className="short-story-resizable-panel"
        defaultSize={SHORT_STORY_PANEL_CONSTRAINTS.workflow.defaultSize}
        groupResizeBehavior="preserve-pixel-size"
        id={SHORT_STORY_PANEL_IDS.workflow}
        maxSize={SHORT_STORY_PANEL_CONSTRAINTS.workflow.maxSize}
        minSize={SHORT_STORY_PANEL_CONSTRAINTS.workflow.minSize}
      >
        {panels[0]}
      </Panel>
      <Separator className="short-story-panel-separator" id="short-story-workflow-separator" />
      <Panel
        className="short-story-resizable-panel"
        groupResizeBehavior="preserve-relative-size"
        id={SHORT_STORY_PANEL_IDS.canvas}
        minSize={SHORT_STORY_PANEL_CONSTRAINTS.canvas.minSize}
      >
        {panels[1]}
      </Panel>
      <Separator className="short-story-panel-separator" id="short-story-chat-separator" />
      <Panel
        className="short-story-resizable-panel"
        defaultSize={SHORT_STORY_PANEL_CONSTRAINTS.chat.defaultSize}
        groupResizeBehavior="preserve-pixel-size"
        id={SHORT_STORY_PANEL_IDS.chat}
        maxSize={SHORT_STORY_PANEL_CONSTRAINTS.chat.maxSize}
        minSize={SHORT_STORY_PANEL_CONSTRAINTS.chat.minSize}
      >
        {panels.at(-1)}
      </Panel>
    </Group>
  );
}
