package cn.inkforge.core.platform.db;

import java.net.URI;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.Set;

/** 将现有 SQLAlchemy PostgreSQL 地址拆成 JDBC 参数，且日志表示永不包含密码。 */
public final class PostgresConnectionSettings {

    private static final Set<String> SUPPORTED_SCHEMES = Set.of("postgresql", "postgresql+asyncpg");

    private final String jdbcUrl;
    private final String username;
    private final String password;
    private final String databaseName;

    private PostgresConnectionSettings(
            String jdbcUrl, String username, String password, String databaseName) {
        this.jdbcUrl = jdbcUrl;
        this.username = username;
        this.password = password;
        this.databaseName = databaseName;
    }

    public static PostgresConnectionSettings parse(String databaseUrl) {
        if (databaseUrl == null || databaseUrl.isBlank()) {
            throw new IllegalArgumentException("DATABASE_URL 不能为空");
        }
        URI uri;
        try {
            uri = URI.create(databaseUrl);
        } catch (IllegalArgumentException exception) {
            throw new IllegalArgumentException("DATABASE_URL 不是有效 URI", exception);
        }
        if (!SUPPORTED_SCHEMES.contains(uri.getScheme())) {
            throw new IllegalArgumentException("DATABASE_URL 必须使用 PostgreSQL 协议");
        }
        if (uri.getHost() == null || uri.getHost().isBlank()) {
            throw new IllegalArgumentException("DATABASE_URL 缺少主机");
        }
        String rawUserInfo = uri.getRawUserInfo();
        int separator = rawUserInfo == null ? -1 : rawUserInfo.indexOf(':');
        if (separator <= 0 || separator == rawUserInfo.length() - 1) {
            throw new IllegalArgumentException("DATABASE_URL 必须包含用户名与密码");
        }
        String rawPath = uri.getRawPath();
        if (rawPath == null || rawPath.length() <= 1 || rawPath.substring(1).contains("/")) {
            throw new IllegalArgumentException("DATABASE_URL 必须包含单一数据库名");
        }

        String username = percentDecode(rawUserInfo.substring(0, separator));
        String password = percentDecode(rawUserInfo.substring(separator + 1));
        String databaseName = percentDecode(rawPath.substring(1));
        String host = uri.getHost().contains(":") ? "[" + uri.getHost() + "]" : uri.getHost();
        String port = uri.getPort() < 0 ? "" : ":" + uri.getPort();
        String query = uri.getRawQuery() == null ? "" : "?" + uri.getRawQuery();
        String jdbcUrl = "jdbc:postgresql://" + host + port + rawPath + query;
        return new PostgresConnectionSettings(jdbcUrl, username, password, databaseName);
    }

    public String jdbcUrl() {
        return jdbcUrl;
    }

    public String username() {
        return username;
    }

    public String password() {
        return password;
    }

    public String databaseName() {
        return databaseName;
    }

    @Override
    public String toString() {
        return "PostgresConnectionSettings[jdbcUrl=" + jdbcUrl + ", username=***, password=***, databaseName="
                + databaseName + "]";
    }

    private static String percentDecode(String value) {
        // URLDecoder 面向表单，会把裸 '+' 当空格；URI user-info 中裸 '+' 应保留原义。
        return URLDecoder.decode(value.replace("+", "%2B"), StandardCharsets.UTF_8);
    }
}
