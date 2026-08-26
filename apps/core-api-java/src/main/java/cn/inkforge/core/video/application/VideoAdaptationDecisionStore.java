package cn.inkforge.core.video.application;

import cn.inkforge.contracts.api.ConfirmAdaptationPlanRequest;
import cn.inkforge.contracts.api.DiscardAdaptationCandidateRequest;
import cn.inkforge.contracts.api.SaveEpisodePlanRequest;
import cn.inkforge.contracts.api.SaveShotPromptRequest;

/** 用户把候选物化为正式方案、分集和逐镜提示词的事务边界。 */
public interface VideoAdaptationDecisionStore {

    String confirmPlan(
            String userId, String adaptationId, ConfirmAdaptationPlanRequest request);

    String saveEpisodePlan(
            String userId, String adaptationId, SaveEpisodePlanRequest request);

    String discardCandidate(
            String userId, String adaptationId, DiscardAdaptationCandidateRequest request);

    String savePrompt(
            String userId,
            String adaptationId,
            String shotId,
            SaveShotPromptRequest request);
}
