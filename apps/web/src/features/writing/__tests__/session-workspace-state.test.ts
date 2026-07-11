import { describe, it } from "node:test";
import assert from "node:assert/strict";

import {
  createEmptySessionWorkspace,
  isCurrentSessionStream,
  reduceSessionWorkspace,
  resolveArtifactInteractionScope,
} from "../session-workspace-state";

type Artifact = { id: string; status: string };

describe("session workspace state", () => {
  it("replaces all session-scoped state when a new session is selected", () => {
    const previous = {
      ...createEmptySessionWorkspace<Artifact>("session-old"),
      taskId: "task-old",
      phase: "recording" as const,
      operationStage: "等待用户决策",
      activeReviewArtifact: { id: "artifact-old", status: "awaiting_user" },
    };

    const next = reduceSessionWorkspace(previous, {
      type: "replace",
      state: createEmptySessionWorkspace<Artifact>("session-new"),
    });

    assert.deepEqual(next, createEmptySessionWorkspace<Artifact>("session-new"));
  });

  it("updates an active artifact without changing the project-level collection", () => {
    const state = createEmptySessionWorkspace<Artifact>("session-1");
    const artifact = { id: "artifact-1", status: "awaiting_user" };

    assert.deepEqual(
      reduceSessionWorkspace(state, { type: "set_active_artifact", artifact }),
      { ...state, activeReviewArtifact: artifact }
    );
  });

  it("rejects a stream that belongs to a previously selected session", () => {
    assert.equal(isCurrentSessionStream("session-new", "session-old"), false);
    assert.equal(isCurrentSessionStream("session-new", "session-new"), true);
  });

  it("treats project backlog artifacts as detached interactions", () => {
    assert.equal(resolveArtifactInteractionScope({
      activeArtifactId: null,
      currentTaskId: null,
      artifactId: "artifact-old",
      artifactTaskId: "task-old",
    }), "artifact");
  });

  it("uses session scope only when both artifact and task match", () => {
    assert.equal(resolveArtifactInteractionScope({
      activeArtifactId: "artifact-1",
      currentTaskId: "task-1",
      artifactId: "artifact-1",
      artifactTaskId: "task-1",
    }), "session");
    assert.equal(resolveArtifactInteractionScope({
      activeArtifactId: "artifact-1",
      currentTaskId: "task-new",
      artifactId: "artifact-1",
      artifactTaskId: "task-old",
    }), "artifact");
  });
});
