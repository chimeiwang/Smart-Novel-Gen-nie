package cn.inkforge.cli.config;

import java.util.Objects;
import java.util.Optional;

/** 使用 macOS Security.framework 保存通用密码，Token 不进入进程参数。 */
public final class MacKeychainCredentialStore implements CredentialStore {

    private final MacKeychainBackend keychain;

    public MacKeychainCredentialStore() {
        this(new NativeMacKeychainBackend());
    }

    MacKeychainCredentialStore(MacKeychainBackend keychain) {
        this.keychain = Objects.requireNonNull(keychain);
    }

    @Override
    public Optional<String> get(String profile, String origin) {
        CredentialKey key = CredentialKey.of(profile, origin);
        String value = keychain.get(key.service(), key.account());
        return value == null || value.isEmpty() ? Optional.empty() : Optional.of(value);
    }

    @Override
    public void set(String profile, String origin, String token) {
        if (token == null || token.isEmpty()) throw new IllegalArgumentException("会话不能为空");
        CredentialKey key = CredentialKey.of(profile, origin);
        keychain.set(key.service(), key.account(), token);
    }

    @Override
    public void delete(String profile, String origin) {
        CredentialKey key = CredentialKey.of(profile, origin);
        keychain.delete(key.service(), key.account());
    }
}
