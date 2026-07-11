import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const legacyActions = [
  "createNovelAction",
  "createChapterAction",
  "saveChapterDraftAction",
  "setChapterStatusAction",
  "updateChapterQualityCheckStatusAction",
  "createCharacterAction",
  "updateCharacterAction",
  "deleteCharacterAction",
  "createCharacterExperienceAction",
  "updateCharacterExperienceAction",
  "deleteCharacterExperienceAction",
  "createCharacterRelationAction",
  "updateCharacterRelationAction",
  "deleteCharacterRelationAction",
  "createItemAction",
  "updateItemAction",
  "deleteItemAction",
  "createLocationAction",
  "updateLocationAction",
  "deleteLocationAction",
  "createFactionAction",
  "updateFactionAction",
  "deleteFactionAction",
  "createGlossaryAction",
  "updateGlossaryAction",
  "deleteGlossaryAction",
  "updateStoryBackgroundAction",
  "updateWorldSettingAction",
  "updateWritingBibleAction",
  "updateStoryProgressAction",
  "updateChapterProgressAction",
  "updateOutlineAction",
  "createOutlineNodeAction",
  "updateOutlineNodeAction",
  "deleteOutlineNodeAction",
  "updatePlotProgressAction",
  "createReferenceMaterialAction",
  "createWritingStyleAction",
  "uploadStyleReferenceAction",
  "deleteStyleReferenceAction",
  "deleteWritingStyleAction",
  "generatePortraitAction",
  "getPortraitTaskStatusAction",
  "applyWritingStyleAction",
  "updateStyleSectionAction",
  "getWritingConfigAction",
  "updateWritingConfigAction",
  "getWritingTaskAction",
  "confirmPlanningAction",
  "acceptGeneratedContentAction",
  "persistUpdatesAction",
  "loginAction",
  "registerAction",
  "logoutAction",
  "getUserTokenStatsAction",
  "getUserCreditSummaryAction",
] as const;

const legacyRoutes = [
  "GET /api/debug/workflow-events",
  "POST /api/portrait/section",
  "POST /api/quality-check/run",
  "POST /api/writing/messages",
  "PUT /api/writing/messages",
  "POST /api/writing/resume",
  "GET /api/writing/review-artifact",
  "POST /api/writing/session",
  "GET /api/writing/sessions",
  "POST /api/writing/sessions",
  "GET /api/writing/sessions/{id}",
  "PATCH /api/writing/sessions/{id}",
  "DELETE /api/writing/sessions/{id}",
  "GET /api/writing/tasks/{taskId}/review-artifact",
] as const;

type Mapping = {
  source: string;
  disposition: "migrated" | "retired";
  method?: string;
  path?: string;
  callers: string[];
  note?: string;
};

test("旧 Next.js 后端入口都有唯一迁移结论", async () => {
  const mappingUrl = new URL(
    "../../../../../../tests/architecture/legacy-backend-map.json",
    import.meta.url,
  );
  const mappings = JSON.parse(await readFile(mappingUrl, "utf8")) as Mapping[];
  const expectedSources = [...legacyActions, ...legacyRoutes].sort();
  const actualSources = mappings.map((item) => item.source).sort();

  assert.deepEqual(actualSources, expectedSources);
  assert.equal(new Set(actualSources).size, actualSources.length, "旧入口不能重复映射");

  for (const mapping of mappings) {
    assert.ok(Array.isArray(mapping.callers), `${mapping.source} 缺少前端调用方清单`);
    if (mapping.disposition === "migrated") {
      assert.match(mapping.method ?? "", /^(GET|POST|PUT|PATCH|DELETE)$/);
      assert.match(mapping.path ?? "", /^\/api\/v1\//);
    } else {
      assert.ok(mapping.note?.trim(), `${mapping.source} 缺少淘汰原因`);
    }
  }
});
