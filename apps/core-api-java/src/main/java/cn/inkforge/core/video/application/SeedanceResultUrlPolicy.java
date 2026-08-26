package cn.inkforge.core.video.application;

import java.net.URI;
import java.util.List;
import java.util.Locale;
import java.util.Objects;
import java.util.regex.Pattern;

/** Seedance 结果下载只允许配置内的公网 HTTPS 域名，防止任意地址出网。 */
public final class SeedanceResultUrlPolicy {

    private static final Pattern IPV4 = Pattern.compile("(?:[0-9]{1,3}\\.){3}[0-9]{1,3}");

    private SeedanceResultUrlPolicy() {}

    public static URI requireAllowed(String value, List<String> allowedHostSuffixes) {
        Objects.requireNonNull(allowedHostSuffixes);
        try {
            URI uri = URI.create(value);
            String host = uri.getHost();
            if (!"https".equals(uri.getScheme())
                    || host == null
                    || host.isBlank()
                    || uri.getRawUserInfo() != null) {
                throw new IllegalArgumentException("SEEDANCE_RESULT_URL_INVALID");
            }
            String normalizedHost = host.toLowerCase(Locale.ROOT);
            if (ipLiteral(normalizedHost)) {
                throw new IllegalArgumentException("SEEDANCE_RESULT_URL_IP_FORBIDDEN");
            }
            boolean allowed = allowedHostSuffixes.stream().anyMatch(suffix ->
                    normalizedHost.endsWith(suffix)
                            && !normalizedHost.equals(suffix.substring(1)));
            if (!allowed) {
                throw new IllegalArgumentException("SEEDANCE_RESULT_HOST_FORBIDDEN");
            }
            return uri;
        } catch (IllegalArgumentException exception) {
            if (exception.getMessage() != null
                    && exception.getMessage().startsWith("SEEDANCE_RESULT_")) {
                throw exception;
            }
            throw new IllegalArgumentException("SEEDANCE_RESULT_URL_INVALID");
        }
    }

    private static boolean ipLiteral(String host) {
        if (host.indexOf(':') >= 0) return true;
        if (!IPV4.matcher(host).matches()) return false;
        for (String part : host.split("\\.")) {
            if (Integer.parseInt(part) > 255) return false;
        }
        return true;
    }
}
