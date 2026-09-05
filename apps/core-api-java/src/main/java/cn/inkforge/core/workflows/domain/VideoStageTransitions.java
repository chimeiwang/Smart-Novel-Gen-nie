package cn.inkforge.core.workflows.domain;

import cn.inkforge.core.workflows.catalog.ExecutionPlanSnapshot;
import cn.inkforge.core.workflows.catalog.VideoStagePolicy;
import cn.inkforge.core.workflows.protocol.ExecutionCanonicalJson;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.LinkedHashSet;

/** 从冻结来源及有序终态事实重建视频下一阶段；模型输出不得自行指定下一次调用。 */
public final class VideoStageTransitions {
    public static final String CORRECTION_REQUIRED = "VIDEO_STAGE_PROTOCOL_CORRECTION_REQUIRED";

    private VideoStageTransitions() {}

    public static Decision replay(ExecutionPlanSnapshot plan, Map<String, Object> context, List<Completed> history) {
        boolean prompt = VideoStagePolicy.PROMPT.equals(plan.videoStagePolicy());
        if (!prompt && !VideoStagePolicy.CINEMATIC.equals(plan.videoStagePolicy())) throw invalid("缺少冻结视频阶段策略");
        Map<String, Object> checkpoint = nullableObject(context.get("inheritedCheckpoint"));
        if (prompt && checkpoint != null) throw invalid("提示词任务不能继承戏剧检查点");
        List<Map<String, Object>> dependencies = new ArrayList<>();
        Map<String, Integer> counts = new LinkedHashMap<>();
        Map<String, Object> expected = prompt ? basic("shot_prompt", 0, false, dependencies, true)
                : checkpoint == null ? basic("dramatic_structure", 0, false, dependencies, true)
                : design(checkpoint, 0, false, List.of(), List.of(), dependencies);
        Decision decision = new Decision(expected, null, null, null);
        Map<String, Object> lastDesign = null;
        for (Completed completed : history) {
            if (decision.nextInput() == null) throw invalid("视频终态之后不能存在其他模型阶段");
            if (!ExecutionCanonicalJson.sha256(expected).equals(ExecutionCanonicalJson.sha256(completed.input()))) {
                throw invalid("视频阶段 input 与冻结来源和前序结果不一致");
            }
            String stage = text(expected, "stageKey");
            int count = counts.merge(stage, 1, Integer::sum);
            if (count > plan.requireVideoStage(stage).maxInvocations()) throw invalid("视频阶段超过冻结调用次数");
            if (completed.stepId() == null || completed.stepId().isBlank()
                    || completed.resultHash() == null || !completed.resultHash().matches("[0-9a-f]{64}")
                    || dependencies.stream().anyMatch(item -> completed.stepId().equals(item.get("stepId")))) {
                throw invalid("视频前序 Step 身份或结果 hash 无效");
            }
            dependencies.add(Map.of("stepId", completed.stepId(), "resultHash", completed.resultHash()));
            int cycle = ((Number) expected.get("cycle")).intValue();
            boolean correction = Boolean.TRUE.equals(expected.get("correction"));
            Map<String, Object> output = completed.output();
            if (completed.errorCode() != null) {
                if (!CORRECTION_REQUIRED.equals(completed.errorCode()) || !completed.correctionAllowed()
                        || !List.of("dramatic_structure", "shot_design", "shot_prompt").contains(stage)) {
                    decision = new Decision(null, null, null, completed.errorCode());
                    continue;
                }
                output = Map.of("stageKey", stage, "outcome", "needs_correction", "validationFindings", List.of(protocolFinding()));
            } else {
                validateOutput(expected, output);
            }
            if (output == null || !stage.equals(output.get("stageKey"))) throw invalid("视频结果阶段与本次 Step 不一致");
            String outcome = text(output, "outcome");
            if ("needs_correction".equals(outcome)) {
                boolean designRetry = "missing_beat_shots".equals(stage) && lastDesign != null
                        && !Boolean.TRUE.equals(lastDesign.get("correction")) && cycle == 0;
                boolean canRetry = completed.correctionAllowed() && (designRetry
                        || cycle == 0 && !correction && List.of("dramatic_structure", "shot_design", "shot_prompt").contains(stage));
                if (!canRetry) {
                    decision = new Decision(null, null, null, "VIDEO_STAGE_CORRECTION_EXHAUSTED");
                    continue;
                }
                List<?> findings = list(output, "validationFindings");
                if (findings.isEmpty()) throw invalid("视频纠正必须保存受控验证发现");
                if ("shot_design".equals(stage) || designRetry) {
                    expected = design(Objects.requireNonNull(checkpoint), 0, true, List.of(), findings, dependencies);
                } else {
                    expected = basic(stage, 0, true, dependencies, true);
                    expected.put("correctionFindings", findings);
                }
            } else if ("dramatic_structure".equals(stage) && "ready".equals(outcome)) {
                checkpoint = object(output.get("checkpoint"));
                expected = design(checkpoint, 0, false, List.of(), List.of(), dependencies);
            } else if ("shot_design".equals(stage)) {
                lastDesign = expected;
                if ("needs_supplement".equals(outcome)) {
                    expected = basic("missing_beat_shots", cycle, false, dependencies, false);
                    expected.put("checkpoint", Objects.requireNonNull(checkpoint));
                    expected.put("design", object(output.get("design")));
                    List<?> missing = list(output, "missingBeatKeys");
                    if (missing.isEmpty()) throw invalid("补槽必须包含明确遗漏 Beat");
                    expected.put("missingBeatKeys", missing);
                } else if ("ready".equals(outcome)) {
                    expected = review(object(output.get("candidate")), cycle, dependencies);
                } else throw invalid("完整设计结果类型无效");
            } else if ("missing_beat_shots".equals(stage) && "ready".equals(outcome)) {
                expected = review(object(output.get("candidate")), cycle, dependencies);
            } else if ("cinematic_review".equals(stage) && "ready".equals(outcome)) {
                Map<String, Object> review = object(output.get("review"));
                String verdict = text(review, "decision");
                if (!List.of("pass", "revise").contains(verdict)) throw invalid("审镜决定无效");
                if (cycle == 0 && "revise".equals(verdict)) {
                    expected = design(Objects.requireNonNull(checkpoint), 1, false, list(review, "requiredChanges"), List.of(), dependencies);
                } else {
                    Map<String, Object> candidate = new LinkedHashMap<>(object(expected.get("candidate")));
                    candidate.put("reviewSummary", nonEmptyText(review, "summary"));
                    candidate.put("reviewFindings", list(review, "findings"));
                    decision = new Decision(null, candidate, null, null);
                    continue;
                }
            } else if ("shot_prompt".equals(stage) && "ready".equals(outcome)) {
                decision = new Decision(null, null, object(output.get("promptBatch")), null);
                continue;
            } else throw invalid("视频阶段结果或有限接续无效");
            String nextStage = text(expected, "stageKey");
            if (counts.getOrDefault(nextStage, 0) >= plan.requireVideoStage(nextStage).maxInvocations()) {
                throw invalid("视频后继超过冻结阶段次数");
            }
            decision = new Decision(expected, null, null, null);
        }
        return decision;
    }

    /** Pydantic 的跨字段 validator 不包含在 JSON Schema 中，Core 接续必须重验同一协议关系。 */
    private static void validateOutput(Map<String, Object> input, Map<String, Object> output) {
        if (output == null) throw invalid("视频阶段缺少完整结果");
        String stage = text(input, "stageKey");
        if (!stage.equals(output.get("stageKey"))) throw invalid("视频结果阶段与本次 Step 不一致");
        Set<String> keys = new LinkedHashSet<>(Set.of("stageKey", "outcome", "validationFindings"));
        keys.addAll(switch (stage) {
            case "dramatic_structure" -> Set.of("checkpoint");
            case "shot_design" -> Set.of("design", "candidate", "missingBeatKeys");
            case "missing_beat_shots" -> Set.of("candidate");
            case "cinematic_review" -> Set.of("review");
            case "shot_prompt" -> Set.of("promptBatch");
            default -> throw invalid("未知视频阶段");
        });
        if (!output.keySet().equals(keys)) throw invalid("视频阶段结果字段集合无效");
        String outcome = text(output, "outcome");
        List<?> findings = list(output, "validationFindings");
        findings.forEach(item -> validateFinding(object(item)));
        boolean ready = "ready".equals(outcome);
        boolean correcting = "needs_correction".equals(outcome);
        switch (stage) {
            case "dramatic_structure", "missing_beat_shots" -> {
                String product = "dramatic_structure".equals(stage) ? "checkpoint" : "candidate";
                if ((!ready && !correcting) || ready != (output.get(product) != null)
                        || correcting != !findings.isEmpty()) {
                    throw invalid("视频阶段结果与规范化产物或纠正发现不一致");
                }
                if (ready) object(output.get(product));
            }
            case "shot_design" -> {
                boolean supplementing = "needs_supplement".equals(outcome);
                List<?> missing = list(output, "missingBeatKeys");
                if ((!ready && !correcting && !supplementing)
                        || ready != (output.get("candidate") != null)
                        || supplementing != (output.get("design") != null && !missing.isEmpty())
                        || correcting != !findings.isEmpty()
                        || !supplementing && (output.get("design") != null || !missing.isEmpty())) {
                    throw invalid("镜头设计结果与候选、缺槽或纠正发现不一致");
                }
                if (ready) object(output.get("candidate"));
                if (supplementing) validateMissingSlots(object(input.get("checkpoint")), object(output.get("design")), missing);
            }
            case "cinematic_review" -> {
                if (!ready) throw invalid("审镜结果只允许 ready");
                Map<String, Object> review = object(output.get("review"));
                String verdict = text(review, "decision");
                List<?> changes = list(review, "requiredChanges");
                if (!List.of("pass", "revise").contains(verdict)
                        || "revise".equals(verdict) != !changes.isEmpty()) {
                    throw invalid("审镜决定与返工要求不一致");
                }
                nonEmptyText(review, "summary");
                list(review, "findings");
            }
            case "shot_prompt" -> {
                if ((!ready && !correcting) || ready && output.get("promptBatch") == null
                        || ready && findings.stream().anyMatch(item -> Boolean.TRUE.equals(object(item).get("blocking")))
                        || correcting && findings.isEmpty()) {
                    throw invalid("提示词结果缺少批次、夹带硬错误或缺少纠正发现");
                }
                if (output.get("promptBatch") != null) object(output.get("promptBatch"));
            }
            default -> throw invalid("未知视频阶段");
        }
    }

    private static void validateFinding(Map<String, Object> finding) {
        if (!finding.keySet().equals(Set.of("code", "shotKey", "parameters", "blocking"))) {
            throw invalid("视频验证发现字段集合无效");
        }
        String code = text(finding, "code");
        Set<String> fields = switch (code) {
            case "prompt_budget" -> Set.of("actual", "maximum");
            case "prompt_action_count" -> Set.of("actual", "maximum", "durationMs");
            case "prompt_scale" -> Set.of("requiredScale", "conflictingScales");
            case "prompt_effects", "prompt_affirmative_effects" -> Set.of("effects");
            case "prompt_unconfirmed_action" -> Set.of("markers");
            case "prompt_repeated_fields" -> Set.of("fields");
            default -> Set.of();
        };
        if (!object(finding.get("parameters")).keySet().equals(fields)) {
            throw invalid("视频验证发现参数必须精确符合该固定错误码");
        }
        boolean structural = Set.of("protocol_invalid", "dramatic_protocol", "dramatic_materialization", "design_protocol",
                "design_materialization", "prompt_schema", "prompt_target_order").contains(code);
        if (structural && (finding.get("shotKey") != null || !Boolean.TRUE.equals(finding.get("blocking")))
                || !structural && finding.get("shotKey") == null) {
            throw invalid("视频验证发现镜号与结构错误范围不一致");
        }
    }

    private static void validateMissingSlots(Map<String, Object> checkpoint, Map<String, Object> design, List<?> missing) {
        List<String> beatKeys = new ArrayList<>();
        for (Object scene : list(checkpoint, "scenes")) {
            for (Object beat : list(object(scene), "beats")) beatKeys.add(text(object(beat), "beatKey"));
        }
        Map<String, Object> slots = object(design.get("beatsByKey"));
        Set<String> expected = new LinkedHashSet<>(beatKeys);
        if (expected.size() != beatKeys.size() || !expected.containsAll(slots.keySet())) {
            throw invalid("补槽设计包含重复或冻结检查点之外的 Beat");
        }
        List<String> actualMissing = beatKeys.stream()
                .filter(key -> !slots.containsKey(key) || list(slots, key).isEmpty()).toList();
        if (!actualMissing.equals(missing)) throw invalid("补槽目标必须精确等于冻结设计的有序缺槽集合");
    }

    private static Map<String, Object> protocolFinding() {
        Map<String, Object> finding = new LinkedHashMap<>();
        finding.put("code", "protocol_invalid");
        finding.put("shotKey", null);
        finding.put("parameters", Map.of());
        finding.put("blocking", true);
        return finding;
    }

    private static Map<String, Object> basic(String stage, int cycle, boolean correction,
            List<Map<String, Object>> dependencies, boolean findings) {
        Map<String, Object> input = new LinkedHashMap<>();
        input.put("stageKey", stage); input.put("cycle", cycle); input.put("correction", correction);
        input.put("dependencies", List.copyOf(dependencies));
        if (findings) input.put("correctionFindings", List.of());
        return input;
    }

    private static Map<String, Object> design(Map<String, Object> checkpoint, int cycle, boolean correction,
            List<?> changes, List<?> findings, List<Map<String, Object>> dependencies) {
        Map<String, Object> input = basic("shot_design", cycle, correction, dependencies, true);
        input.put("checkpoint", checkpoint); input.put("requiredChanges", changes); input.put("correctionFindings", findings);
        return input;
    }

    private static Map<String, Object> review(Map<String, Object> candidate, int cycle, List<Map<String, Object>> dependencies) {
        Map<String, Object> input = basic("cinematic_review", cycle, false, dependencies, false);
        input.put("candidate", candidate);
        return input;
    }

    private static List<?> list(Map<String, Object> object, String key) {
        if (!(object.get(key) instanceof List<?> result)) throw invalid("视频阶段缺少数组：" + key);
        return List.copyOf(result);
    }

    private static String text(Map<String, Object> object, String key) {
        if (!(object.get(key) instanceof String result) || result.isBlank()) throw invalid("视频阶段缺少文本：" + key);
        return result;
    }

    private static String nonEmptyText(Map<String, Object> object, String key) {
        if (!(object.get(key) instanceof String result) || result.isEmpty()) throw invalid("视频阶段缺少非空文本：" + key);
        return result;
    }

    private static Map<String, Object> nullableObject(Object value) {
        return value == null ? null : object(value);
    }

    private static Map<String, Object> object(Object value) {
        if (!(value instanceof Map<?, ?> raw)) throw invalid("视频阶段产物必须是完整对象");
        Map<String, Object> result = new LinkedHashMap<>();
        raw.forEach((key, item) -> {
            if (!(key instanceof String text)) throw invalid("视频阶段对象字段必须为文本");
            result.put(text, item);
        });
        return result;
    }

    private static IllegalStateException invalid(String message) { return new IllegalStateException(message); }

    public record Completed(String stepId, String resultHash, Map<String, Object> input, Map<String, Object> output,
            String errorCode, boolean correctionAllowed) {}

    public record Decision(Map<String, Object> nextInput, Map<String, Object> candidate,
            Map<String, Object> promptBatch, String errorCode) {}
}
