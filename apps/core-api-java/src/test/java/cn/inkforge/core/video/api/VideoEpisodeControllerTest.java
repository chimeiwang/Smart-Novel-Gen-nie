package cn.inkforge.core.video.api;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import cn.inkforge.contracts.api.UpdateVideoEpisodeRequest;
import cn.inkforge.core.generated.api.VideoepisodesApi;
import cn.inkforge.core.identity.application.AuthenticatedUser;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.video.application.VideoEpisodeRepository;
import cn.inkforge.core.video.application.VideoEpisodeService;
import java.util.Arrays;
import java.util.Optional;
import java.util.Set;
import java.util.stream.Collectors;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.openapitools.jackson.nullable.JsonNullable;
import org.openapitools.jackson.nullable.JsonNullableJackson3Module;
import org.springframework.http.ResponseEntity;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

class VideoEpisodeControllerTest {
    private final JsonMapper json=JsonMapper.builder().findAndAddModules().addModule(new JsonNullableJackson3Module()).build();

    @Test void 全部独立剧集公共方法必须显式实现(){
        Set<String> required=Arrays.stream(VideoepisodesApi.class.getDeclaredMethods()).filter(m->ResponseEntity.class.isAssignableFrom(m.getReturnType())).map(m->m.getName()).collect(Collectors.toSet());
        Set<String> actual=Arrays.stream(VideoEpisodeController.class.getDeclaredMethods()).map(m->m.getName()).collect(Collectors.toSet());
        assertThat(required).hasSize(20);assertThat(actual).containsAll(required);
    }

    @Test void 修改请求必须区分省略目标时长与显式清空(){
        VideoEpisodeService service=mock(VideoEpisodeService.class);
        when(service.update(eq("owner"),eq("episode"),any())).thenReturn(json.createObjectNode());
        var controller=new VideoEpisodeController(Optional.of(service),Optional.empty(),Optional.of(token->new AuthenticatedUser("owner","作者")),json);
        var request=new UpdateVideoEpisodeRequest("request-episode-update-01",1);
        request.setTitle(JsonNullable.of("改名"));
        controller.updateVideoEpisodeApiV1VideoEpisodesEpisodeIdPatch("episode",request,"cookie");
        ArgumentCaptor<JsonNode> captured=ArgumentCaptor.forClass(JsonNode.class);verify(service).update(eq("owner"),eq("episode"),captured.capture());
        assertThat(captured.getValue().has("targetDurationSeconds")).isFalse();
        request.setTargetDurationSeconds(JsonNullable.of(null));
        assertThat(json.valueToTree(request).path("targetDurationSeconds").isNull()).isTrue();
    }

    @Test void 关闭视频时写命令不得到达仓储但历史读取仍使用归属端口(){
        VideoEpisodeRepository repository=mock(VideoEpisodeRepository.class);var service=new VideoEpisodeService(repository,false);
        assertThatThrownBy(()->service.create("owner","project",json.createObjectNode())).isInstanceOfSatisfying(ApiException.class,e->assertThat(e.code()).isEqualTo("VIDEO_PREVIEW_DISABLED"));
        verifyNoInteractions(repository);service.get("owner","episode");verify(repository).get("owner","episode");
    }
}
