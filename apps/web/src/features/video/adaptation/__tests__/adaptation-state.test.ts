import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  addShotAfter,
  bindShotSource,
  buildSourceSegments,
  candidateSourceCoverage,
  deleteCandidateShot,
  durationMetrics,
  flattenCandidateShots,
  mergeShotWithNext,
  mergeSceneWithNext,
  restoreCandidateShot,
} from "../adaptation-state";
import type { AdaptationCandidate } from "../types";

function candidate(): AdaptationCandidate {
  return {
    schemaVersion: "chapter_adaptation_plan_v2",
    adaptationId: "adaptation-1",
    sourceHash: "a".repeat(64),
    suggestedEpisodeBreakAfterShotKeys: [],
    scenes: [{
      sceneKey: "SC01",
      title: "雨夜书房",
      locationLabel: "书房",
      timeLabel: "雨夜",
      objective: "确认线索",
      changeSummary: "等待变成危险预警",
      beats: [{
        beatKey: "B01",
        title: "钥匙揭示危险",
        dramaticTurn: "人物意识到危险",
        visualStrategy: "空间、反应和物件揭示",
        sourceRanges: [{ start: 0, end: 8, sourceText: "甲乙丙丁戊己庚辛" }],
        shots: [
          {
            shotKey: "S01",
            title: "建立书房",
            narrativePurpose: "establishing",
            adaptationType: "supplemental",
            shotScale: "long",
            cameraAngle: "eye_level",
            cameraMovement: "locked",
            visualIntent: "建立空间",
            audioMode: "ambient",
            audioIntent: "雨声",
            cutReason: "进入新场景先建立空间",
            timelineDurationMs: 2000,
            sourceRanges: [],
          },
          {
            shotKey: "S02",
            title: "钥匙落桌",
            narrativePurpose: "reveal",
            adaptationType: "direct",
            shotScale: "close",
            cameraAngle: "eye_level",
            cameraMovement: "push_in",
            visualIntent: "钥匙落桌",
            audioMode: "ambient",
            audioIntent: "金属声",
            cutReason: "关键物件改变信息量",
            timelineDurationMs: 1500,
            sourceRanges: [{ start: 0, end: 4, sourceText: "甲乙丙丁" }],
          },
        ],
      }],
    }],
  };
}

describe("章节影视化候选纯状态", () => {
  it("新增镜头只进入当前戏剧节拍并连续重编号", () => {
    const next = addShotAfter(
      candidate(),
      "S01",
      { start: 4, end: 8, sourceText: "戊己庚辛" },
      "reaction",
    );
    assert.ok(next);
    assert.deepEqual(flattenCandidateShots(next).map((shot) => shot.shotKey), ["S01", "S02", "S03"]);
    assert.equal(flattenCandidateShots(next)[1]?.narrativePurpose, "reaction");
  });

  it("不允许删除戏剧节拍中的最后一个镜头", () => {
    const value = candidate();
    value.scenes[0]!.beats[0]!.shots = [value.scenes[0]!.beats[0]!.shots[0]!];
    assert.equal(deleteCandidateShot(value, "S01"), null);
  });

  it("删除恢复和合并保持连续镜号", () => {
    const deleted = deleteCandidateShot(candidate(), "S02");
    assert.ok(deleted);
    const restored = restoreCandidateShot(deleted.plan, deleted.discarded);
    assert.ok(restored);
    assert.deepEqual(flattenCandidateShots(restored).map((shot) => shot.shotKey), ["S01", "S02"]);
    const merged = mergeShotWithNext(restored, "S01");
    assert.ok(merged);
    assert.equal(flattenCandidateShots(merged).length, 1);
  });

  it("选区重绑会同步扩展所属戏剧节拍来源", () => {
    const next = bindShotSource(
      candidate(),
      "S01",
      { start: 8, end: 12, sourceText: "壬癸子丑" },
    );

    assert.deepEqual(next.scenes[0]?.beats[0]?.sourceRanges, [
      { start: 0, end: 8, sourceText: "甲乙丙丁戊己庚辛" },
      { start: 8, end: 12, sourceText: "壬癸子丑" },
    ]);
    assert.deepEqual(next.scenes[0]?.beats[0]?.shots[0]?.sourceRanges, [
      { start: 8, end: 12, sourceText: "壬癸子丑" },
    ]);
  });

  it("合并镜头超过十五秒时明确拒绝而不静默压缩", () => {
    const value = candidate();
    value.scenes[0]!.beats[0]!.shots[0]!.timelineDurationMs = 8000;
    value.scenes[0]!.beats[0]!.shots[1]!.timelineDurationMs = 8000;

    assert.equal(mergeShotWithNext(value, "S01"), null);
  });

  it("计算原文覆盖和短视频节奏分布", () => {
    const value = candidate();
    assert.equal(candidateSourceCoverage(value, 8), 50);
    assert.deepEqual(buildSourceSegments("甲乙丙丁戊己庚辛", value).map((item) => item.shotKeys), [
      ["S02"],
      [],
    ]);
    assert.deepEqual(durationMetrics(flattenCandidateShots(value)), {
      totalMs: 3500,
      averageMs: 1750,
      fastCount: 2,
      standardCount: 0,
      slowCount: 0,
    });
  });

  it("合并相邻场景并保留其中全部戏剧节拍", () => {
    const value = candidate();
    value.scenes.push({
      ...value.scenes[0]!,
      sceneKey: "SC02",
      title: "二层平台",
      locationLabel: "黄铜匣前",
      timeLabel: "第九声钟后",
      beats: [{ ...value.scenes[0]!.beats[0]!, beatKey: "B02" }],
    });
    const merged = mergeSceneWithNext(value, "SC01");
    assert.ok(merged);
    assert.equal(merged.scenes.length, 1);
    assert.equal(merged.scenes[0]?.beats.length, 2);
    assert.equal(merged.scenes[0]?.locationLabel, "书房 / 黄铜匣前");
    assert.equal(merged.scenes[0]?.timeLabel, "雨夜 / 第九声钟后");
    assert.deepEqual(merged.scenes[0]?.beats.map((beat) => beat.beatKey), ["B01", "B02"]);
  });
});
