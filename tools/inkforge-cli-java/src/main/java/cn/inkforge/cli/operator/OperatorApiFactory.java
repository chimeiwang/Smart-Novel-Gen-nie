package cn.inkforge.cli.operator;

import cn.inkforge.cli.runtime.CliInputException;
import cn.inkforge.cli.transport.CoreApi;
import cn.inkforge.cli.transport.CoreApiClient;
import cn.inkforge.cli.transport.CoreOrigin;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.Proxy;
import java.net.ProxySelector;
import java.net.SocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.time.Duration;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import tools.jackson.databind.ObjectMapper;

/** Operator 只连接固定 Core；回环直连，生产显式解释代理环境变量。 */
public final class OperatorApiFactory {

    private OperatorApiFactory() {}

    /** 只为当前 Operator 模式绑定的固定 origin 创建 Core 客户端。 */
    public static CoreApi create(
            String mode,
            Map<String, String> environment,
            ObjectMapper json,
            String origin,
            String token) {
        String normalized = CoreOrigin.validate(origin);
        String expected = switch (mode) {
            case "local" -> "http://127.0.0.1:8000";
            case "production" -> "https://inkforge.cn";
            default -> throw new CliInputException("OPERATOR_MODE_INVALID", "Operator 环境无效");
        };
        if (!expected.equals(normalized)) {
            throw new CliInputException("OPERATOR_ORIGIN_MISMATCH", "Operator 不能连接未绑定的 Core 地址", 3);
        }
        return new CoreApiClient(normalized, token, json, client(mode, environment));
    }

    static HttpClient client(String mode, Map<String, String> environment) {
        Proxy proxy = switch (mode) {
            case "local" -> Proxy.NO_PROXY;
            case "production" -> configuredProxy(URI.create("https://inkforge.cn"), environment);
            default -> throw new CliInputException("OPERATOR_MODE_INVALID", "Operator 环境无效");
        };
        return HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(30))
                .followRedirects(HttpClient.Redirect.NEVER)
                .proxy(new FixedProxySelector(proxy))
                .build();
    }

    /** 解析代理与 no_proxy；不支持的协议或凭据配置明确失败。 */
    static Proxy configuredProxy(URI destination, Map<String, String> environment) {
        if (bypass(destination, value(environment, "no_proxy"))) return Proxy.NO_PROXY;
        String configured = value(environment, destination.getScheme().toLowerCase(Locale.ROOT) + "_proxy");
        if (configured.isEmpty()) configured = value(environment, "all_proxy");
        if (configured.isEmpty()) return Proxy.NO_PROXY;
        URI address;
        try {
            address = URI.create(configured.contains("://") ? configured : "http://" + configured);
        } catch (IllegalArgumentException exception) {
            throw invalidProxy();
        }
        if (!"http".equalsIgnoreCase(address.getScheme())) {
            throw new CliInputException(
                    "OPERATOR_PROXY_UNSUPPORTED",
                    "Java Operator 当前仅支持 http:// 代理，不支持 HTTPS 或 SOCKS 代理协议");
        }
        if (address.getRawUserInfo() != null) {
            throw new CliInputException(
                    "OPERATOR_PROXY_UNSUPPORTED",
                    "Java Operator 当前不支持带账号密码的代理，请使用本机无凭据 HTTP 代理");
        }
        if (address.getHost() == null
                || address.getHost().isBlank()
                || address.getRawQuery() != null
                || address.getRawFragment() != null
                || !List.of("", "/").contains(address.getRawPath())) {
            throw invalidProxy();
        }
        int port = address.getPort() == -1 ? 80 : address.getPort();
        if (port < 1 || port > 65535) throw invalidProxy();
        return new Proxy(Proxy.Type.HTTP, new InetSocketAddress(address.getHost(), port));
    }

    private static CliInputException invalidProxy() {
        return new CliInputException("OPERATOR_PROXY_INVALID", "代理配置无效，请检查代理协议、主机和端口");
    }

    private static String value(Map<String, String> environment, String lowerName) {
        String raw = environment.containsKey(lowerName)
                ? environment.get(lowerName)
                : environment.get(lowerName.toUpperCase(Locale.ROOT));
        return raw == null ? "" : raw.trim();
    }

    /** 判断目标是否匹配 no_proxy 的主机、子域、端口或协议规则。 */
    private static boolean bypass(URI destination, String exclusions) {
        String host = bareHost(destination.getHost());
        int port = destination.getPort() == -1
                ? ("https".equalsIgnoreCase(destination.getScheme()) ? 443 : 80)
                : destination.getPort();
        for (String entry : exclusions.split(",")) {
            String pattern = entry.trim().toLowerCase(Locale.ROOT);
            if (pattern.isEmpty()) continue;
            if (pattern.equals("*")) return true;
            String matchHost;
            int matchPort = -1;
            if (pattern.contains("://")) {
                URI address;
                try {
                    address = URI.create(pattern);
                } catch (IllegalArgumentException exception) {
                    continue;
                }
                if (!destination.getScheme().equalsIgnoreCase(address.getScheme())) continue;
                matchHost = bareHost(address.getHost());
                matchPort = address.getPort();
            } else if (pattern.startsWith("[")) {
                int closing = pattern.indexOf(']');
                if (closing < 0) continue;
                matchHost = pattern.substring(1, closing);
                if (closing + 1 < pattern.length()) {
                    if (pattern.charAt(closing + 1) != ':') continue;
                    matchPort = parsePort(pattern.substring(closing + 2));
                    if (matchPort == -1) continue;
                }
            } else {
                int colon = pattern.lastIndexOf(':');
                if (colon >= 0 && pattern.indexOf(':') == colon) {
                    matchPort = parsePort(pattern.substring(colon + 1));
                    if (matchPort == -1) continue;
                    pattern = pattern.substring(0, colon);
                }
                matchHost = pattern;
            }
            if (matchPort != -1 && matchPort != port) continue;
            if (matchHost.startsWith("*.")) matchHost = matchHost.substring(2);
            else if (matchHost.startsWith(".")) matchHost = matchHost.substring(1);
            if (!matchHost.isEmpty()
                    && (host.equals(matchHost) || host.endsWith("." + matchHost))) return true;
        }
        return false;
    }

    private static int parsePort(String value) {
        try {
            int port = Integer.parseInt(value);
            return port >= 1 && port <= 65535 ? port : -1;
        } catch (NumberFormatException exception) {
            return -1;
        }
    }

    private static String bareHost(String host) {
        if (host == null) return "";
        String result = host.toLowerCase(Locale.ROOT);
        return result.startsWith("[") && result.endsWith("]")
                ? result.substring(1, result.length() - 1)
                : result;
    }

    private static final class FixedProxySelector extends ProxySelector {

        private final List<Proxy> proxies;

        private FixedProxySelector(Proxy proxy) {
            proxies = List.of(proxy);
        }

        @Override
        public List<Proxy> select(URI uri) {
            return proxies;
        }

        @Override
        public void connectFailed(URI uri, SocketAddress address, IOException failure) {
            // 不回退为直连，也不把可能包含代理凭据的异常写入输出。
        }
    }
}
