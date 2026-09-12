package cn.inkforge.core.contract;

import static org.assertj.core.api.Assertions.assertThat;

import cn.inkforge.core.generated.api.BillingApi;
import cn.inkforge.core.generated.api.ChaptersApi;
import cn.inkforge.core.generated.api.DebugApi;
import cn.inkforge.core.generated.api.IdentityApi;
import cn.inkforge.core.generated.api.LoreApi;
import cn.inkforge.core.generated.api.NovelsApi;
import cn.inkforge.core.generated.api.OperationsApi;
import cn.inkforge.core.generated.api.OutlinesApi;
import cn.inkforge.core.generated.api.QualityApi;
import cn.inkforge.core.generated.api.ReferencesApi;
import cn.inkforge.core.generated.api.ReviewsApi;
import cn.inkforge.core.generated.api.ShortmediumApi;
import cn.inkforge.core.generated.api.StylesApi;
import cn.inkforge.core.generated.api.VideoApi;
import cn.inkforge.core.generated.api.VideoepisodeimpactsApi;
import cn.inkforge.core.generated.api.VideoepisodepostproductionApi;
import cn.inkforge.core.generated.api.VideoepisoderendersApi;
import cn.inkforge.core.generated.api.VideoepisodesApi;
import cn.inkforge.core.generated.api.VideoproductionApi;
import cn.inkforge.core.generated.api.WorkflowsApi;
import cn.inkforge.core.generated.api.WritingApi;
import cn.inkforge.core.operations.api.HealthController;
import java.io.IOException;
import java.lang.reflect.Method;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.config.BeanDefinition;
import org.springframework.context.support.GenericApplicationContext;
import org.springframework.context.annotation.ClassPathScanningCandidateComponentProvider;
import org.springframework.core.type.filter.AnnotationTypeFilter;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestMethod;
import org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerMapping;
import org.springframework.web.method.HandlerMethod;
import org.springframework.web.servlet.mvc.method.RequestMappingInfo;
import org.mockito.Mockito;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

/** 仅通过 Spring MVC 实际 HandlerMethod 核对 207 条 canonical 路由，不启动业务数据库。 */
class CoreRouteCoverageTest {

    private static final List<Class<?>> GENERATED_APIS = List.of(
            BillingApi.class, ChaptersApi.class, DebugApi.class, IdentityApi.class, LoreApi.class,
            NovelsApi.class, OperationsApi.class, OutlinesApi.class, QualityApi.class,
            ReferencesApi.class, ReviewsApi.class, ShortmediumApi.class, StylesApi.class,
            VideoApi.class, VideoepisodeimpactsApi.class, VideoepisodepostproductionApi.class,
            VideoepisoderendersApi.class, VideoepisodesApi.class, VideoproductionApi.class,
            WorkflowsApi.class, WritingApi.class);

    @Test
    void 生成接口和健康Controller必须覆盖canonical的207条路由() throws Exception {
        Map<Route, ContractRoute> contract = readContractRoutes();
        Map<Route, GeneratedRoute> generated = generatedRoutes(contract);
        Map<Route, ActualRoute> actual = springRoutes();

        assertThat(generated).hasSize(207);
        assertThat(actual).containsOnlyKeys(contract.keySet());
        assertThat(actual).containsOnlyKeys(generated.keySet());
        assertThat(contract.keySet()).containsExactlyInAnyOrderElementsOf(actual.keySet());
        assertThat(contract.keySet().stream().filter(route -> route.path().startsWith("/api/v1/")).count())
                .isEqualTo(183);
        assertThat(contract.keySet().stream().filter(route -> route.path().startsWith("/internal/v1/")).count())
                .isEqualTo(24);
        assertThat(contract.values().stream().filter(route -> route.exposure().equals("public")).count())
                .isEqualTo(182);
        assertThat(contract.values().stream().filter(route -> route.exposure().equals("provider_media")).count())
                .isEqualTo(1);

        for (Map.Entry<Route, GeneratedRoute> entry : generated.entrySet()) {
            ActualRoute mapped = actual.get(entry.getKey());
            assertThat(mapped).as("生成方法没有真实 Spring Handler: %s", entry.getKey()).isNotNull();
            assertThat(mapped.handler().getMethod().getDeclaringClass())
                    .as("生成方法不能直接由接口处理: %s", entry.getKey())
                    .isNotEqualTo(entry.getValue().api());
            if (entry.getValue().api() != OperationsApi.class) {
                assertThat(mapped.handler().getMethod().getName())
                        .as("Controller 未覆盖生成方法: %s", entry.getKey())
                        .isEqualTo(entry.getValue().method().getName());
                assertThat(entry.getValue().api().isAssignableFrom(mapped.handler().getBeanType()))
                        .as("Handler 所属 Controller 未实现生成接口: %s", entry.getKey())
                        .isTrue();
            } else {
                assertThat(HealthController.class.isAssignableFrom(mapped.handler().getBeanType()))
                        .as("健康接口必须映射到 HealthController: %s", entry.getKey())
                        .isTrue();
            }
        }

        for (Map.Entry<Route, ActualRoute> entry : actual.entrySet()) {
            ContractRoute expected = contract.get(entry.getKey());
            ActualRoute mapped = entry.getValue();
            assertThat(mapped.consumes()).as("consumes 漂移: %s", entry.getKey())
                    .isEqualTo(expected.consumes());
            assertThat(mapped.produces()).as("produces 漂移: %s", entry.getKey())
                    .isEqualTo(expected.produces());
            assertThat(mapped.handler().getMethod().getDeclaringClass())
                    .as("Handler 不能直接是生成接口: %s", entry.getKey())
                    .isNotIn(GENERATED_APIS);
        }
        assertThat(HealthController.class.isAssignableFrom(
                actual.get(new Route("GET", "/api/v1/health/live")).handler().getBeanType())).isTrue();
        assertThat(HealthController.class.isAssignableFrom(
                actual.get(new Route("GET", "/api/v1/health/ready")).handler().getBeanType())).isTrue();
    }

    private static Map<Route, GeneratedRoute> generatedRoutes(Map<Route, ContractRoute> contract) {
        Map<Route, GeneratedRoute> result = new LinkedHashMap<>();
        for (Class<?> api : GENERATED_APIS) {
            for (Method method : api.getDeclaredMethods()) {
                RequestMapping mapping = method.getAnnotation(RequestMapping.class);
                assertThat(mapping).as("生成方法缺少 RequestMapping: %s", method).isNotNull();
                for (String path : paths(mapping.value(), mapping.path())) {
                    for (RequestMethod httpMethod : mapping.method()) {
                        Route route = new Route(httpMethod.name(), path);
                        assertThat(contract).as("生成接口路由未登记: %s", route).containsKey(route);
                        assertThat(result.put(route, new GeneratedRoute(api, method)))
                                .as("生成接口重复路由: %s", route).isNull();
                    }
                }
            }
        }
        return result;
    }

    private static Map<Route, ActualRoute> springRoutes() {
        Set<Class<?>> controllers = findControllers();
        try (GenericApplicationContext context = new GenericApplicationContext()) {
            for (Class<?> controller : controllers) registerMockController(context, controller);
            context.registerBean(RequestMappingHandlerMapping.class);
            context.refresh();
            RequestMappingHandlerMapping mapping = context.getBean(RequestMappingHandlerMapping.class);
            Map<Route, ActualRoute> result = new LinkedHashMap<>();
            for (Map.Entry<RequestMappingInfo, HandlerMethod> entry : mapping.getHandlerMethods().entrySet()) {
                RequestMappingInfo info = entry.getKey();
                for (String path : paths(info)) {
                    if (!path.startsWith("/api/v1/") && !path.startsWith("/internal/v1/")) continue;
                    for (RequestMethod method : info.getMethodsCondition().getMethods()) {
                        Route route = new Route(method.name(), path);
                        ActualRoute actual = new ActualRoute(route, mediaTypes(info.getConsumesCondition().getConsumableMediaTypes()),
                                mediaTypes(info.getProducesCondition().getProducibleMediaTypes()), entry.getValue());
                        assertThat(result.put(route, actual)).as("Spring Handler 重复路由: %s", route).isNull();
                    }
                }
            }
            return result;
        }
    }

    private static <T> void registerMockController(GenericApplicationContext context, Class<T> controller) {
        context.registerBean(controller, () -> Mockito.mock(controller));
    }

    private static Set<Class<?>> findControllers() {
        ClassPathScanningCandidateComponentProvider scanner =
                new ClassPathScanningCandidateComponentProvider(false);
        // 契约覆盖启用 V2 回调门禁，但只注册 mock，不触碰数据库或启动业务后台任务。
        var environment = new org.springframework.core.env.StandardEnvironment();
        environment.getPropertySources().addFirst(new org.springframework.core.env.MapPropertySource(
                "contract-test", Map.of("DURABLE_AGENT_EXECUTION_SCHEMA_READY", "true")));
        scanner.setEnvironment(environment);
        scanner.addIncludeFilter(new AnnotationTypeFilter(Controller.class));
        Set<Class<?>> result = new LinkedHashSet<>();
        for (BeanDefinition candidate : scanner.findCandidateComponents("cn.inkforge.core")) {
            try {
                result.add(Class.forName(candidate.getBeanClassName(), false,
                        CoreRouteCoverageTest.class.getClassLoader()));
            } catch (ClassNotFoundException exception) {
                throw new IllegalStateException("无法加载 Controller: " + candidate.getBeanClassName(), exception);
            }
        }
        assertThat(result).contains(HealthController.class);
        return result;
    }

    private static Map<Route, ContractRoute> readContractRoutes() throws IOException {
        JsonNode document = new ObjectMapper().readTree(findContract().toFile());
        Map<Route, ContractRoute> result = new LinkedHashMap<>();
        document.path("paths").properties().forEach(pathEntry -> pathEntry.getValue().properties()
                .forEach(methodEntry -> {
                    String method = methodEntry.getKey().toUpperCase();
                    if (!Set.of("GET", "POST", "PUT", "PATCH", "DELETE").contains(method)) return;
                    JsonNode operation = methodEntry.getValue();
                    Set<String> consumes = operation.has("requestBody")
                            ? propertyNames(operation.path("requestBody").path("content")) : Set.of();
                    Set<String> produces = new LinkedHashSet<>();
                    operation.path("responses").properties().forEach(response -> {
                        // Spring 的 produces 包含同一路由的成功媒体与 JSON 错误响应。
                        response.getValue().path("content").propertyNames().forEach(produces::add);
                    });
                    Route route = new Route(method, pathEntry.getKey());
                        result.put(route, new ContractRoute(
                                route, consumes, produces, operation.path("x-inkforge-exposure").textValue()));
                }));
        return result;
    }

    private static Set<String> propertyNames(JsonNode object) {
        Set<String> names = new LinkedHashSet<>();
        object.propertyNames().forEach(names::add);
        return names;
    }

    private static Set<String> mediaTypes(Set<MediaType> values) {
        return values.stream().map(MediaType::toString).collect(java.util.stream.Collectors.toSet());
    }

    private static Set<String> paths(RequestMappingInfo info) {
        if (info.getPathPatternsCondition() != null) {
            return info.getPathPatternsCondition().getPatternValues();
        }
        return info.getPatternsCondition().getPatterns();
    }

    private static String[] paths(String[] value, String[] path) {
        return value.length == 0 ? path : value;
    }

    private static Path findContract() {
        Path current = Path.of(System.getProperty("user.dir")).toAbsolutePath().normalize();
        while (current != null) {
            Path candidate = current.resolve("contracts/core/openapi.json");
            if (Files.isRegularFile(candidate)) return candidate;
            current = current.getParent();
        }
        throw new IllegalStateException("找不到 contracts/core/openapi.json");
    }

    private record Route(String method, String path) {}

    private record ContractRoute(Route route, Set<String> consumes, Set<String> produces, String exposure) {}

    private record GeneratedRoute(Class<?> api, Method method) {}

    private record ActualRoute(Route route, Set<String> consumes, Set<String> produces, HandlerMethod handler) {}
}
