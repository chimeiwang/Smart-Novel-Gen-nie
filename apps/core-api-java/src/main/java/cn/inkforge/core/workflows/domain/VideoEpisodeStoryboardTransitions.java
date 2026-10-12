package cn.inkforge.core.workflows.domain;

import static cn.inkforge.core.workflows.domain.VideoEpisodeStoryboardDocuments.*;

import cn.inkforge.core.workflows.catalog.ExecutionPlanSnapshot;
import cn.inkforge.core.workflows.catalog.VideoStagePolicy;
import cn.inkforge.core.workflows.protocol.ExecutionCanonicalJson;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

/** 分镜固定为起草、审片及至多一次返工；终态只准备作者可选候选。 */
public final class VideoEpisodeStoryboardTransitions {
    private VideoEpisodeStoryboardTransitions() {}

    public static Map<String, Object> initialInput() {
        return input("episode_storyboard", 0, null, List.of(), List.of());
    }

    public static Decision replay(
            ExecutionPlanSnapshot plan,
            Map<String, Object> context,
            List<Completed> history) {
        if (!VideoStagePolicy.EPISODE_STORYBOARD.equals(plan.videoStagePolicy())
                || history.size() > 4) {
            throw invalid("单集分镜必须使用冻结有限阶段策略");
        }
        Map<String, Object> expected = initialInput();
        Map<String, Object> candidate = null;
        Map<String, Object> candidateDependency = null;
        int cycle = 0;
        Decision decision = new Decision(expected, null, null);
        for (Completed step : history) {
            if (decision.nextInput() == null
                    || !ExecutionCanonicalJson.sha256(expected)
                            .equals(ExecutionCanonicalJson.sha256(step.input()))) {
                throw invalid("分镜前序阶段不是 Core 推导的唯一接续");
            }
            Map<String, Object> output = step.output();
            String stage = text(expected.get("stageKey"));
            if (!stage.equals(output.get("stageKey"))) {
                throw invalid("分镜结果阶段不一致");
            }
            Map<String, Object> dependency =
                    Map.of("stepId", step.stepId(), "resultHash", step.resultHash());
            if (stage.equals("episode_storyboard")) {
                if (output.get("review") != null) throw invalid("分镜起草不能伪造审片结果");
                candidate = object(output.get("candidate"));
                merge(context, candidate);
                candidateDependency = dependency;
                expected = input(
                        "episode_storyboard_review",
                        cycle,
                        candidate,
                        List.of(),
                        List.of(dependency));
            } else {
                if (candidate == null || output.get("candidate") != null) {
                    throw invalid("分镜审片不能替换候选");
                }
                Map<String, Object> review = object(output.get("review"));
                Map<String, Object> document = merge(context, candidate);
                validateReview(context, document, review);
                String verdict = text(review.get("decision"));
                List<?> changes = list(review.get("requiredChanges"));
                if ((!verdict.equals("pass") && !verdict.equals("revise"))
                        || verdict.equals("revise") != !changes.isEmpty()) {
                    throw invalid("分镜审片结论与返工要求不一致");
                }
                if (verdict.equals("pass") || cycle == 1) {
                    decision = new Decision(null, document, review);
                    continue;
                }
                cycle = 1;
                expected = input(
                        "episode_storyboard",
                        cycle,
                        candidate,
                        changes,
                        List.of(Objects.requireNonNull(candidateDependency), dependency));
            }
            decision = new Decision(expected, null, null);
        }
        return decision;
    }

    private static Map<String, Object> input(
            String stage,
            int cycle,
            Map<String, Object> candidate,
            List<?> changes,
            List<?> dependencies) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("stageKey", stage);
        result.put("cycle", cycle);
        result.put("candidate", candidate);
        result.put("requiredChanges", changes);
        result.put("dependencies", dependencies);
        return java.util.Collections.unmodifiableMap(result);
    }

    public record Completed(
            String stepId,
            String resultHash,
            Map<String, Object> input,
            Map<String, Object> output) {}

    public record Decision(
            Map<String, Object> nextInput,
            Map<String, Object> document,
            Map<String, Object> review) {}
}
