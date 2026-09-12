package cn.inkforge.core;

import static org.assertj.core.api.Assertions.assertThat;

import cn.inkforge.core.generated.api.OperationsApi;
import cn.inkforge.core.generated.api.WritingApi;
import java.lang.reflect.Method;
import org.junit.jupiter.api.Test;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestMethod;

/** 验证生成 API 的特殊边界；完整路由集合由 CoreRouteCoverageTest 双向核对。 */
class GeneratedApiCoverageTest {

    @Test
    void 健康接口和写作接口必须保留生成映射元数据() throws Exception {
        assertThat(OperationsApi.class.getDeclaredMethods()).hasSize(2);
        assertMapping(OperationsApi.class, "liveApiV1HealthLiveGet", "/api/v1/health/live", RequestMethod.GET);
        assertMapping(OperationsApi.class, "readyApiV1HealthReadyGet", "/api/v1/health/ready", RequestMethod.GET);
        assertThat(findWritingMethod("createWritingSessionApiV1WritingSessionsPost")).isNotNull();
    }

    private static Method findWritingMethod(String name) {
        for (Method method : WritingApi.class.getDeclaredMethods()) {
            if (method.getName().equals(name)) return method;
        }
        return null;
    }

    private static void assertMapping(
            Class<?> api, String methodName, String path, RequestMethod requestMethod) throws Exception {
        Method method = api.getDeclaredMethod(methodName);
        RequestMapping mapping = method.getAnnotation(RequestMapping.class);
        assertThat(mapping).isNotNull();
        assertThat(mapping.value()).containsExactly(path);
        assertThat(mapping.method()).containsExactly(requestMethod);
    }
}
