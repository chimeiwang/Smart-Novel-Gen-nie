package cn.inkforge.core.identity.infrastructure;

import cn.inkforge.core.identity.domain.PasswordCodec;
import cn.inkforge.core.platform.http.ApiException;
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import org.springframework.security.crypto.bcrypt.BCrypt;

/** 按 bcryptjs 的 UTF-8 前 72 字节和成本 12 保持历史密码兼容。 */
public final class BCryptPasswordCodec implements PasswordCodec {

    private static final int BCRYPT_BYTES = 72;

    @Override
    public String hash(String password) {
        try {
            return BCrypt.hashpw(encoded(password), BCrypt.gensalt("$2b", 12));
        } catch (CharacterCodingException exception) {
            throw new ApiException(
                    400,
                    "INVALID_PASSWORD_ENCODING",
                    "密码包含无效字符");
        }
    }

    @Override
    public boolean matches(String password, String passwordHash) {
        try {
            return BCrypt.checkpw(encoded(password), passwordHash);
        } catch (RuntimeException | CharacterCodingException exception) {
            return false;
        }
    }

    private static byte[] encoded(String password) throws CharacterCodingException {
        ByteBuffer bytes = StandardCharsets.UTF_8.newEncoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .encode(CharBuffer.wrap(password));
        byte[] value = new byte[bytes.remaining()];
        bytes.get(value);
        return value.length <= BCRYPT_BYTES ? value : Arrays.copyOf(value, BCRYPT_BYTES);
    }
}
