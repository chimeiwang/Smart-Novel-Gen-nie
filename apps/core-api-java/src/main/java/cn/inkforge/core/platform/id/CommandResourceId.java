package cn.inkforge.core.platform.id;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

/** 把幂等创建请求稳定映射为与 Python {@code command_resource_id} 相同的资源 ID。 */
public final class CommandResourceId {

    private CommandResourceId() {}

    public static String derive(
            String namespace, String userId, String novelId, String requestId) {
        String payload = String.join("\u001f", namespace, userId, novelId, requestId);
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(payload.getBytes(StandardCharsets.UTF_8));
            return "ifc_" + HexFormat.of().formatHex(digest);
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("JDK 缺少 SHA-256", exception);
        }
    }
}
