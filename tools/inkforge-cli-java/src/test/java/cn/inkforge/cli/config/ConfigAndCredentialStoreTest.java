package cn.inkforge.cli.config;

import static org.assertj.core.api.Assertions.assertThat;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import tools.jackson.databind.json.JsonMapper;

class ConfigAndCredentialStoreTest {

    @Test
    void 配置文件只保存profile的origin和用户名(@TempDir Path directory) throws Exception {
        Path path = directory.resolve("config.json");
        JsonConfigStore store = new JsonConfigStore(path, JsonMapper.builder().build());

        store.save("default", new ProfileConfig("https://inkforge.cn", "nie"));
        store.save("dev", new ProfileConfig("http://127.0.0.1:8000", "dev-user"));

        assertThat(store.get("default"))
                .contains(new ProfileConfig("https://inkforge.cn", "nie"));
        assertThat(store.get("dev"))
                .contains(new ProfileConfig("http://127.0.0.1:8000", "dev-user"));
        String serialized = Files.readString(path);
        assertThat(serialized)
                .contains("\"schemaVersion\": 1", "\"profiles\"")
                .doesNotContain("token", "Cookie", "password");

        store.delete("default");
        assertThat(store.get("default")).isEmpty();
        assertThat(store.get("dev")).isPresent();
    }

    @Test
    void 安全凭据键绑定规范化origin且凭据只进入后端() {
        FakeKeychain backend = new FakeKeychain();
        CredentialStore store = new MacKeychainCredentialStore(backend);

        store.set("default", "https://INKFORGE.CN/", "session-secret");

        assertThat(backend.values).hasSize(1);
        String key = backend.values.keySet().iterator().next();
        assertThat(key).startsWith("InkForge CLI/").contains("\0inkforge-token:default");
        assertThat(key).doesNotContain("inkforge.cn");
        assertThat(store.get("default", "https://inkforge.cn"))
                .contains("session-secret");
        store.delete("default", "https://inkforge.cn");
        assertThat(store.get("default", "https://inkforge.cn")).isEmpty();
    }

    @Test
    void Windows凭据兼容PythonKeyring复合Target和UTF16格式() {
        FakeWindowsCredentials backend = new FakeWindowsCredentials();
        CredentialStore store = new WindowsCredentialStore(backend);

        store.set("default", "https://inkforge.cn", "default-secret");
        store.set("dev", "https://inkforge.cn", "dev-secret");

        assertThat(store.get("default", "https://inkforge.cn"))
                .contains("default-secret");
        assertThat(store.get("dev", "https://inkforge.cn"))
                .contains("dev-secret");
        assertThat(backend.values).hasSize(2);
        assertThat(backend.values.keySet()).anyMatch(target -> target.contains("@InkForge CLI/"));

        store.delete("default", "https://inkforge.cn");
        assertThat(store.get("default", "https://inkforge.cn")).isEmpty();
        assertThat(store.get("dev", "https://inkforge.cn")).contains("dev-secret");
    }

    private static final class FakeKeychain implements MacKeychainBackend {

        private final Map<String, String> values = new HashMap<>();

        @Override
        public String get(String service, String account) {
            return values.get(service + "\0" + account);
        }

        @Override
        public void set(String service, String account, String secret) {
            values.put(service + "\0" + account, secret);
        }

        @Override
        public void delete(String service, String account) {
            values.remove(service + "\0" + account);
        }
    }

    private static final class FakeWindowsCredentials implements WindowsCredentialBackend {

        private final Map<String, StoredCredential> values = new HashMap<>();

        @Override
        public StoredCredential get(String target) {
            StoredCredential value = values.get(target);
            return value == null
                    ? null
                    : new StoredCredential(value.account(), value.secret().clone());
        }

        @Override
        public void set(String target, String account, byte[] secret) {
            values.put(target, new StoredCredential(account, secret.clone()));
        }

        @Override
        public void delete(String target) {
            values.remove(target);
        }
    }
}
