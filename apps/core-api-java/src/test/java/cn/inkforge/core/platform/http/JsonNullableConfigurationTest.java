package cn.inkforge.core.platform.http;

import static org.assertj.core.api.Assertions.assertThat;

import cn.inkforge.contracts.api.PlotProgressRequest;
import org.junit.jupiter.api.Test;
import org.openapitools.jackson.nullable.JsonNullableJackson3Module;
import tools.jackson.databind.cfg.ConstructorDetector;
import tools.jackson.databind.json.JsonMapper;

class JsonNullableConfigurationTest {

    @Test
    void 有默认构造器时不得推断必填参数构造器() throws Exception {
        JsonMapper mapper = JsonMapper.builder()
                .constructorDetector(
                        ConstructorDetector.DEFAULT.withAllowImplicitWithDefaultConstructor(false))
                .addModule(new JsonNullableJackson3Module())
                .build();

        PlotProgressRequest missing = mapper.readValue(
                "{\"currentStage\":\"第一幕\"}", PlotProgressRequest.class);
        PlotProgressRequest explicitNull = mapper.readValue(
                "{\"currentStage\":\"第一幕\",\"expectedUpdatedAt\":null}",
                PlotProgressRequest.class);

        assertThat(missing.getExpectedUpdatedAt().isUndefined()).isTrue();
        assertThat(explicitNull.getExpectedUpdatedAt().isPresent()).isTrue();
        assertThat(explicitNull.getExpectedUpdatedAt().orElse(null)).isNull();
    }
}
