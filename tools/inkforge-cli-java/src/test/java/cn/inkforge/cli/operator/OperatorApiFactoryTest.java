package cn.inkforge.cli.operator;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.cli.runtime.CliInputException;
import cn.inkforge.cli.transport.CoreTransportException;
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.ServerSocket;
import java.nio.charset.StandardCharsets;
import java.net.InetSocketAddress;
import java.net.Proxy;
import java.net.URI;
import java.net.http.HttpClient;
import java.util.Map;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.json.JsonMapper;

class OperatorApiFactoryTest {

    private static final URI PRODUCTION = URI.create("https://inkforge.cn");

    @Test
    void 本地模式强制直连且不解析代理配置() {
        HttpClient client = OperatorApiFactory.client("local", Map.of(
                "HTTP_PROXY", "无效代理", "HTTPS_PROXY", "socks5://代理", "ALL_PROXY", "https://代理"));
        assertThat(client.proxy().orElseThrow().select(URI.create("http://127.0.0.1:8000")))
                .containsExactly(Proxy.NO_PROXY);
        assertThat(client.followRedirects()).isEqualTo(HttpClient.Redirect.NEVER);
    }

    @Test
    void 工厂拒绝跨环境地址和内部服务但不需要执行网络请求() {
        var json = JsonMapper.builder().build();
        assertThatThrownBy(() -> OperatorApiFactory.create(
                "local", Map.of(), json, "https://inkforge.cn", null))
                .isInstanceOfSatisfying(CliInputException.class,
                        error -> assertThat(error.code()).isEqualTo("OPERATOR_ORIGIN_MISMATCH"));
        assertThatThrownBy(() -> OperatorApiFactory.create(
                "production", Map.of(), json, "http://127.0.0.1:8000", null))
                .isInstanceOf(CliInputException.class);
        var api = OperatorApiFactory.create("production", Map.of(), json, "https://inkforge.cn", null);
        assertThatThrownBy(() -> api.request("GET", "/internal/v1/runs"))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void 生产使用HTTPS代理并遵循小写优先和ALL代理回退() {
        assertProxy(OperatorApiFactory.configuredProxy(PRODUCTION, Map.of(
                "HTTP_PROXY", "http://127.0.0.1:8001",
                "HTTPS_PROXY", "http://127.0.0.1:8002",
                "https_proxy", "http://127.0.0.1:8003",
                "ALL_PROXY", "http://127.0.0.1:8004")), 8003);
        assertProxy(OperatorApiFactory.configuredProxy(PRODUCTION, Map.of(
                "HTTPS_PROXY", "http://127.0.0.1:8002",
                "https_proxy", "",
                "ALL_PROXY", "127.0.0.1:8004")), 8004);
        assertThat(OperatorApiFactory.configuredProxy(PRODUCTION, Map.of(
                "HTTP_PROXY", "http://127.0.0.1:8001"))).isEqualTo(Proxy.NO_PROXY);
        assertProxy(OperatorApiFactory.configuredProxy(URI.create("http://inkforge.cn"), Map.of(
                "HTTP_PROXY", "http://127.0.0.1:8001")), 8001);
        assertProxy(OperatorApiFactory.client("production", Map.of(
                "HTTPS_PROXY", "http://127.0.0.1:8002"))
                .proxy().orElseThrow().select(PRODUCTION).getFirst(), 8002);
    }

    @Test
    void 真实HTTP客户端向本机代理发送CONNECT但不直接连接生产() throws Exception {
        try (ServerSocket proxy = new ServerSocket();
                var executor = Executors.newVirtualThreadPerTaskExecutor()) {
            proxy.bind(new InetSocketAddress("127.0.0.1", 0));
            proxy.setSoTimeout(3000);
            var captured = executor.submit(() -> {
                try (var socket = proxy.accept()) {
                    socket.setSoTimeout(3000);
                    var reader = new BufferedReader(new InputStreamReader(
                            socket.getInputStream(), StandardCharsets.US_ASCII));
                    StringBuilder headers = new StringBuilder();
                    String line;
                    while ((line = reader.readLine()) != null && !line.isEmpty()) {
                        headers.append(line).append('\n');
                    }
                    socket.getOutputStream().write(
                            "HTTP/1.1 503 Service Unavailable\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
                                    .getBytes(StandardCharsets.US_ASCII));
                    socket.getOutputStream().flush();
                    return headers.toString();
                }
            });
            var api = OperatorApiFactory.create("production", Map.of(
                    "HTTPS_PROXY", "http://127.0.0.1:" + proxy.getLocalPort()),
                    JsonMapper.builder().build(), "https://inkforge.cn", "synthetic-proxy-test-token");
            assertThatThrownBy(() -> api.request("GET", "/api/v1/auth/me"))
                    .isInstanceOf(CoreTransportException.class);
            assertThat(captured.get(4, TimeUnit.SECONDS))
                    .startsWith("CONNECT inkforge.cn:443 HTTP/1.1\n")
                    .doesNotContain("synthetic-proxy-test-token", "inkforge-token");
        }
    }

    @Test
    void NO代理支持域名端口与通配但不误匹配相似域名() {
        for (String bypass : new String[] {
            "*", "inkforge.cn", ".inkforge.cn", "*.inkforge.cn", "inkforge.cn:443",
            "其他.invalid, inkforge.cn", "https://inkforge.cn"
        }) {
            assertThat(OperatorApiFactory.configuredProxy(PRODUCTION, Map.of(
                    "HTTPS_PROXY", "http://127.0.0.1:8002", "NO_PROXY", bypass)))
                    .as(bypass).isEqualTo(Proxy.NO_PROXY);
        }
        for (String keepProxy : new String[] {
            "inkforge.cn:80", "forge.cn", "evilinkforge.cn", "http://inkforge.cn"
        }) {
            assertProxy(OperatorApiFactory.configuredProxy(PRODUCTION, Map.of(
                    "HTTPS_PROXY", "http://127.0.0.1:8002", "NO_PROXY", keepProxy)), 8002);
        }
        assertProxy(OperatorApiFactory.configuredProxy(PRODUCTION, Map.of(
                "HTTPS_PROXY", "http://127.0.0.1:8002", "NO_PROXY", "*", "no_proxy", "")), 8002);
    }

    @Test
    void 不支持或无效代理必须明确拒绝且不泄露凭据() {
        for (String unsupported : new String[] {
            "socks5://127.0.0.1:9000", "https://127.0.0.1:9000", "http://用户名:测试密码@127.0.0.1:9000"
        }) {
            assertThatThrownBy(() -> OperatorApiFactory.configuredProxy(PRODUCTION, Map.of(
                    "HTTPS_PROXY", unsupported)))
                    .isInstanceOfSatisfying(CliInputException.class,
                            error -> assertThat(error.code()).isEqualTo("OPERATOR_PROXY_UNSUPPORTED"))
                    .hasMessageNotContaining("测试密码");
        }
        assertThatThrownBy(() -> OperatorApiFactory.configuredProxy(PRODUCTION, Map.of(
                "HTTPS_PROXY", "http://127.0.0.1:70000")))
                .isInstanceOfSatisfying(CliInputException.class,
                        error -> assertThat(error.code()).isEqualTo("OPERATOR_PROXY_INVALID"));
    }

    private static void assertProxy(Proxy proxy, int port) {
        assertThat(proxy.type()).isEqualTo(Proxy.Type.HTTP);
        assertThat(proxy.address()).isEqualTo(new InetSocketAddress("127.0.0.1", port));
    }
}
