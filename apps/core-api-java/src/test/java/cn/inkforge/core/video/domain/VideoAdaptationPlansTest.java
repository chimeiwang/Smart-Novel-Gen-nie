package cn.inkforge.core.video.domain;

import static cn.inkforge.core.video.support.VideoAdaptationFixtures.candidate;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.core.platform.http.ApiException;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.json.JsonMapper;

class VideoAdaptationPlansTest {

    @Test
    void Unicode来源校验和规范哈希必须与Python契约一致() {
        var plan = candidate("adaptation-1", "甲😀乙");

        VideoAdaptationPlans.validateAgainstSource(
                plan, "adaptation-1", "甲😀乙", plan.getSourceHash());

        assertThat(VideoAdaptationPlans.contentHash(
                        plan, JsonMapper.builder().findAndAddModules().build()))
                .isEqualTo("7963eba08fa22241abd615e4b6a3bae3c72ab486777f24ec5003a8a0cf4323b5");
        assertThatThrownBy(() -> VideoAdaptationPlans.validateAgainstSource(
                        plan, "adaptation-1", "甲😁乙", plan.getSourceHash()))
                .isInstanceOfSatisfying(ApiException.class, exception ->
                        assertThat(exception.code()).isEqualTo("VIDEO_ADAPTATION_SOURCE_INVALID"));
    }

    @Test
    void 必须拒绝机械切镜理由和不连续镜头Key() {
        var mechanical = candidate("adaptation-1", "甲😀乙");
        mechanical.getScenes().getFirst().getBeats().getFirst().getShots().getFirst()
                .setCutReason("说话人变化");
        assertThatThrownBy(() -> VideoAdaptationPlans.validateCandidate(mechanical))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("机械切镜");

        var discontinuous = candidate("adaptation-1", "甲😀乙");
        discontinuous.getScenes().getFirst().getBeats().getFirst().getShots().getFirst()
                .setShotKey("S02");
        assertThatThrownBy(() -> VideoAdaptationPlans.validateCandidate(discontinuous))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("S01");
    }
}
