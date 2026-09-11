package cn.inkforge.core.video.api;

import static org.assertj.core.api.Assertions.assertThat;

import cn.inkforge.core.generated.api.VideoepisodeimpactsApi;
import cn.inkforge.core.generated.api.VideoepisodepostproductionApi;
import cn.inkforge.core.generated.api.VideoepisoderendersApi;
import cn.inkforge.core.generated.api.VideoproductionApi;
import java.util.Arrays;
import java.util.Set;
import java.util.stream.Collectors;
import org.junit.jupiter.api.Test;
import org.springframework.http.ResponseEntity;

class VideoProductionControllerTest {

    @Test
    void 分镜制作公共方法必须全部由明确控制器实现() {
        assertImplementsAll(VideoproductionApi.class, VideoProductionController.class, 19);
    }

    @Test
    void 影响复核公共方法必须全部由明确控制器实现() {
        assertImplementsAll(
                VideoepisodeimpactsApi.class, VideoEpisodeImpactController.class, 3);
    }

    @Test
    void 逐镜生成公共方法必须全部由明确控制器实现() {
        assertImplementsAll(
                VideoepisoderendersApi.class, VideoEpisodeRenderController.class, 4);
    }

    @Test
    void 基础后期公共方法必须全部由明确控制器实现() {
        assertImplementsAll(
                VideoepisodepostproductionApi.class,
                VideoEpisodePostProductionController.class,
                11);
    }

    private static void assertImplementsAll(
            Class<?> contract, Class<?> implementation, int expectedCount) {
        Set<String> required = Arrays.stream(contract.getDeclaredMethods())
                .filter(method -> ResponseEntity.class.isAssignableFrom(method.getReturnType()))
                .map(method -> method.getName())
                .collect(Collectors.toSet());
        Set<String> actual = Arrays.stream(implementation.getDeclaredMethods())
                .map(method -> method.getName())
                .collect(Collectors.toSet());

        assertThat(required).hasSize(expectedCount);
        assertThat(actual).containsAll(required);
    }
}
