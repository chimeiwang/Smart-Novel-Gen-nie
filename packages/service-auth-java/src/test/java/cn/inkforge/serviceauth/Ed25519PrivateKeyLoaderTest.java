package cn.inkforge.serviceauth;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermission;
import java.security.KeyPairGenerator;
import java.security.Signature;
import java.util.Base64;
import java.util.Set;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class Ed25519PrivateKeyLoaderTest {

    @TempDir
    Path temporaryDirectory;

    @Test
    void 公共加载入口必须复用受控PKCS8文件读取并返回可用私钥() throws Exception {
        var keyPair = KeyPairGenerator.getInstance("Ed25519").generateKeyPair();
        Path keyFile = temporaryDirectory.resolve("core.pem");
        Files.writeString(keyFile, pem(keyPair.getPrivate().getEncoded()), StandardCharsets.US_ASCII);
        ownerOnly(keyFile);

        var loaded = Ed25519PrivateKeyLoader.fromPkcs8File(keyFile);
        byte[] content = "inkforge-model-grant".getBytes(StandardCharsets.UTF_8);
        Signature signer = Signature.getInstance("Ed25519");
        signer.initSign(loaded);
        signer.update(content);
        Signature verifier = Signature.getInstance("Ed25519");
        verifier.initVerify(keyPair.getPublic());
        verifier.update(content);

        assertThat(verifier.verify(signer.sign())).isTrue();
    }

    @Test
    void 公共加载入口必须拒绝符号链接() throws Exception {
        var keyPair = KeyPairGenerator.getInstance("Ed25519").generateKeyPair();
        Path keyFile = temporaryDirectory.resolve("real.pem");
        Files.writeString(keyFile, pem(keyPair.getPrivate().getEncoded()), StandardCharsets.US_ASCII);
        ownerOnly(keyFile);
        Path link = temporaryDirectory.resolve("linked.pem");
        Files.createSymbolicLink(link, keyFile);

        assertThatThrownBy(() -> Ed25519PrivateKeyLoader.fromPkcs8File(link))
                .isInstanceOf(ServiceAuthException.class)
                .hasMessage("无法加载 Ed25519 PKCS8 私钥");
    }

    private static String pem(byte[] bytes) {
        return "-----BEGIN PRIVATE KEY-----\n"
                + Base64.getMimeEncoder(64, new byte[] {'\n'}).encodeToString(bytes)
                + "\n-----END PRIVATE KEY-----\n";
    }

    private static void ownerOnly(Path path) throws Exception {
        try {
            Files.setPosixFilePermissions(
                    path,
                    Set.of(PosixFilePermission.OWNER_READ, PosixFilePermission.OWNER_WRITE));
        } catch (UnsupportedOperationException ignored) {
            // 非 POSIX 文件系统由生产加载器跳过权限位检查，测试保持同一兼容策略。
        }
    }
}
