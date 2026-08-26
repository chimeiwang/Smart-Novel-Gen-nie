package cn.inkforge.cli.transport;

import java.net.URI;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

/** Core origin 的唯一安全规范化入口。 */
public final class CoreOrigin {

    public static final String INSECURE_HTTP_ORIGIN_ENV =
            "INKFORGE_CLI_ALLOW_INSECURE_HTTP_ORIGIN";
    private static final Set<String> LOOPBACK = Set.of("localhost", "127.0.0.1", "::1");

    private CoreOrigin() {}

    public static String validate(String value) {
        return validate(value, System.getenv());
    }

    public static String validate(String value, Map<String, String> environment) {
        Normalized normalized = normalize(value);
        if (normalized.scheme().equals("http") && !LOOPBACK.contains(normalized.host())) {
            String configured = Objects.requireNonNull(environment).get(INSECURE_HTTP_ORIGIN_ENV);
            String allowed = null;
            if (configured != null) {
                try {
                    allowed = normalize(configured).value();
                } catch (IllegalArgumentException ignored) {
                    // 无效放行值与未配置等价，不能扩大远程 HTTP 范围。
                }
            }
            if (!normalized.value().equals(allowed)) {
                throw new IllegalArgumentException("HTTP 仅允许连接本机回环地址，远程地址必须使用 HTTPS");
            }
        }
        return normalized.value();
    }

    private static Normalized normalize(String value) {
        if (value == null || value.isEmpty() || !value.equals(value.trim())) {
            throw new IllegalArgumentException("Core API 地址不能为空或包含首尾空白");
        }
        URI uri;
        try {
            uri = URI.create(value);
        } catch (IllegalArgumentException exception) {
            throw new IllegalArgumentException("Core API 地址无效", exception);
        }
        String scheme = uri.getScheme() == null
                ? ""
                : uri.getScheme().toLowerCase(Locale.ROOT);
        if (!Set.of("http", "https").contains(scheme)) {
            throw new IllegalArgumentException("Core API 仅支持 HTTP 或 HTTPS");
        }
        if (uri.getUserInfo() != null) {
            throw new IllegalArgumentException("Core API 地址不得包含用户信息");
        }
        String host = uri.getHost();
        if (host == null || host.isBlank()) {
            throw new IllegalArgumentException("Core API 地址缺少主机名");
        }
        if (host.startsWith("[") && host.endsWith("]")) {
            host = host.substring(1, host.length() - 1);
        }
        host = host.toLowerCase(Locale.ROOT);
        String path = uri.getRawPath();
        if (!(path == null || path.isEmpty() || path.equals("/"))
                || uri.getRawQuery() != null
                || uri.getRawFragment() != null) {
            throw new IllegalArgumentException("Core API 地址只能包含 origin，不得包含路径、查询或片段");
        }
        String renderedHost = host.contains(":") ? "[" + host + "]" : host;
        String renderedPort = uri.getPort() < 0 ? "" : ":" + uri.getPort();
        return new Normalized(scheme + "://" + renderedHost + renderedPort, scheme, host);
    }

    private record Normalized(String value, String scheme, String host) {}
}
