/**
 * 运行方式：npx tsx --test src/shared/contracts/__tests__/agent-update-channels.test.ts
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import "@/agents/tools";
import { getOpenAITools } from "@/agents/tools/registry";
import {
  ForbiddenToolTextSectionsShape,
  isItemTextBlockFieldAllowed,
} from "../agent-update-channels";
import { parseControlEventArgsDetailed } from "../agent-control";

describe("Agent update channel contract", () => {
  it("keeps long top-level text sections out of short tool updates", () => {
    for (const section of ["outlineContent", "worldSetting", "storyBackground"] as const) {
      assert.ok(ForbiddenToolTextSectionsShape[section], `${section} should be forbidden`);

      const result = parseControlEventArgsDetailed("append_update_batch", {
        artifactKey: "channel-test",
        updates: {
          [section]: "长文本必须走 put_update_text_block",
        },
      });

      assert.equal(result.success, false);
      if (result.success) continue;
      assert.ok(result.error.issues.some((issue) => issue.path === `updates.${section}`));
    }
  });

  it("keeps append_outline_tree structure-only in parser and OpenAI schema", () => {
    const result = parseControlEventArgsDetailed("append_outline_tree", {
      artifactKey: "channel-test",
      stages: [
        {
          title: "第一阶段",
          content: "阶段长内容不得进入树工具参数",
          plotUnits: [
            {
              title: "剧情单元",
              content: "单元长内容不得进入树工具参数",
              chapterGroups: [
                {
                  title: "前三章",
                  content: "章节组长梗概不得进入树工具参数",
                },
              ],
            },
          ],
        },
      ],
    });

    assert.equal(result.success, false);
    if (!result.success) {
      assert.ok(result.error.issues.some((issue) => issue.path === "stages.0.content"));
      assert.ok(result.error.issues.some((issue) => issue.path === "stages.0.plotUnits.0.content"));
      assert.ok(result.error.issues.some((issue) => issue.path === "stages.0.plotUnits.0.chapterGroups.0.content"));
    }

    const tool = getOpenAITools(["append_outline_tree"])[0];
    const params = tool.function.parameters as {
      additionalProperties?: boolean;
      properties?: {
        stages?: {
          items?: {
            additionalProperties?: boolean;
            properties?: Record<string, unknown>;
          };
        };
      };
    };
    const stageSchema = params.properties?.stages?.items;

    assert.equal(params.additionalProperties, false);
    assert.equal(stageSchema?.additionalProperties, false);
    assert.equal(stageSchema?.properties?.content, undefined);
  });

  it("defines item long-text block fields by section", () => {
    assert.equal(isItemTextBlockFieldAllowed("outlineAdjustments", "content"), true);
    assert.equal(isItemTextBlockFieldAllowed("outlineAdjustments", "description"), false);
    assert.equal(isItemTextBlockFieldAllowed("characters", "background"), true);
    assert.equal(isItemTextBlockFieldAllowed("characters", "content"), false);
    assert.equal(isItemTextBlockFieldAllowed("locations", "climate"), true);
    assert.equal(isItemTextBlockFieldAllowed("items", "effect"), true);
    assert.equal(isItemTextBlockFieldAllowed("foreshadowing", "payoffNote"), true);
  });
});
