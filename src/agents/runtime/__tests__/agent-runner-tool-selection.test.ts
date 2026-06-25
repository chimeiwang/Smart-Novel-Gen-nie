/**
 * AgentRunner tool exposure tests.
 *
 * These tests lock the boundary between an Agent's declared capabilities and
 * the OpenAI tools it can see.
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import "@/agents/tools";
import { getOpenAITools } from "@/agents/tools/registry";
import { getToolNamesForAgent } from "../agent-runner";

describe("AgentRunner tool selection", () => {
  it("does not expose update builder tools to the editor Agent", () => {
    const toolNames = getToolNamesForAgent({
      id: "编辑",
      toolCapabilities: [
        "novel.read",
        "character.read",
        "plot.read",
        "chapter.read",
        "style.read",
        "artifact.read",
        "control.quality",
        "control.evaluation",
        "control.revision",
        "control.route",
      ],
    });

    assert.ok(toolNames.includes("route_to_agent"));
    assert.ok(toolNames.includes("request_revision"));
    assert.ok(toolNames.includes("submit_evaluation"));
    assert.ok(toolNames.includes("get_agent_capability_cards"));
    assert.equal(toolNames.includes("start_update_builder"), false);
    assert.equal(toolNames.includes("append_update_batch"), false);
    assert.equal(toolNames.includes("append_outline_tree"), false);
    assert.equal(toolNames.includes("put_update_text_block"), false);
    assert.equal(toolNames.includes("put_update_item_text_block"), false);
    assert.equal(toolNames.includes("put_update_item_text_blocks"), false);
    assert.equal(toolNames.includes("finish_update_builder"), false);
    assert.equal(toolNames.includes("propose_updates"), false);
  });

  it("exposes update builder tools to the plot Agent", () => {
    const toolNames = getToolNamesForAgent({
      id: "剧情",
      toolCapabilities: [
        "novel.read",
        "character.read",
        "plot.read",
        "chapter.read",
        "artifact.read",
        "proposal.plot",
        "control.proposal",
        "control.builder",
        "control.route",
      ],
    });

    assert.ok(toolNames.includes("route_to_agent"));
    assert.ok(toolNames.includes("propose_updates"));
    assert.ok(toolNames.includes("start_update_builder"));
    assert.ok(toolNames.includes("append_update_batch"));
    assert.ok(toolNames.includes("append_outline_tree"));
    assert.ok(toolNames.includes("put_update_text_block"));
    assert.ok(toolNames.includes("put_update_item_text_block"));
    assert.ok(toolNames.includes("put_update_item_text_blocks"));
    assert.ok(toolNames.includes("finish_update_builder"));
  });

  it("only exposes append_outline_tree to the plot Agent", () => {
    const commonBuilderCapabilities = ["control.builder", "control.route"];
    const cases: Array<{ id: "设定" | "写作" | "校验" | "编辑"; capabilities: string[] }> = [
      { id: "设定", capabilities: commonBuilderCapabilities },
      { id: "写作", capabilities: commonBuilderCapabilities },
      { id: "校验", capabilities: commonBuilderCapabilities },
      { id: "编辑", capabilities: commonBuilderCapabilities },
    ];

    for (const item of cases) {
      const toolNames = getToolNamesForAgent({
        id: item.id,
        toolCapabilities: item.capabilities,
      });
      assert.equal(toolNames.includes("append_outline_tree"), false, item.id);
    }
  });

  it("append_outline_tree OpenAI schema is structure-only and rejects extra fields", () => {
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
    assert.equal(Boolean(stageSchema?.properties?.content), false);
  });

  it("honors tool agentIds in addition to capability", () => {
    const toolNames = getToolNamesForAgent({
      id: "写作",
      toolCapabilities: ["control.evaluation", "control.revision", "control.route"],
    });

    assert.ok(toolNames.includes("route_to_agent"));
    assert.equal(toolNames.includes("submit_evaluation"), false);
    assert.equal(toolNames.includes("request_revision"), false);
  });

  it("exposes review artifact display tool through control.artifact", () => {
    const toolNames = getToolNamesForAgent({
      id: "编辑",
      toolCapabilities: ["artifact.read", "control.artifact"],
    });

    assert.ok(toolNames.includes("show_review_artifact"));
  });
});
