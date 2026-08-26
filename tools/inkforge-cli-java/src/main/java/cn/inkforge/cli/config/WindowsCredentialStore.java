package cn.inkforge.cli.config;

import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.Optional;

/** 使用 Windows Credential Manager，并兼容 Python keyring 的复合 target 规则。 */
public final class WindowsCredentialStore implements CredentialStore {

    private final WindowsCredentialBackend backend;

    public WindowsCredentialStore() {
        this(new NativeWindowsCredentialBackend());
    }

    WindowsCredentialStore(WindowsCredentialBackend backend) {
        this.backend = backend;
    }

    @Override
    public Optional<String> get(String profile, String origin) {
        CredentialKey key = CredentialKey.of(profile, origin);
        WindowsCredentialBackend.StoredCredential stored = backend.get(key.service());
        if (stored == null || !stored.account().equals(key.account())) {
            wipe(stored);
            stored = backend.get(compound(key));
        }
        if (stored == null || !stored.account().equals(key.account())) {
            wipe(stored);
            return Optional.empty();
        }
        byte[] secret = stored.secret();
        try {
            String value = decode(secret);
            return value.isEmpty() ? Optional.empty() : Optional.of(value);
        } finally {
            Arrays.fill(secret, (byte) 0);
        }
    }

    @Override
    public void set(String profile, String origin, String token) {
        if (token == null || token.isEmpty()) throw new IllegalArgumentException("会话不能为空");
        CredentialKey key = CredentialKey.of(profile, origin);
        WindowsCredentialBackend.StoredCredential existing = backend.get(key.service());
        try {
            if (existing != null && !existing.account().equals(key.account())) {
                backend.set(compound(existing.account(), key.service()), existing.account(), existing.secret());
            }
        } finally {
            wipe(existing);
        }
        byte[] secret = token.getBytes(StandardCharsets.UTF_16LE);
        try {
            backend.set(key.service(), key.account(), secret);
        } finally {
            Arrays.fill(secret, (byte) 0);
        }
    }

    @Override
    public void delete(String profile, String origin) {
        CredentialKey key = CredentialKey.of(profile, origin);
        deleteIfOwned(key.service(), key.account());
        deleteIfOwned(compound(key), key.account());
    }

    private void deleteIfOwned(String target, String account) {
        WindowsCredentialBackend.StoredCredential stored = backend.get(target);
        try {
            if (stored != null && stored.account().equals(account)) backend.delete(target);
        } finally {
            wipe(stored);
        }
    }

    private static String decode(byte[] secret) {
        if (looksUtf16Le(secret)) return new String(secret, StandardCharsets.UTF_16LE);
        return new String(secret, StandardCharsets.UTF_8);
    }

    private static boolean looksUtf16Le(byte[] secret) {
        if (secret.length < 2 || secret.length % 2 != 0) return false;
        int zeros = 0;
        for (int index = 1; index < secret.length; index += 2) {
            if (secret[index] == 0) zeros++;
        }
        return zeros * 5 >= secret.length / 2;
    }

    private static String compound(CredentialKey key) {
        return compound(key.account(), key.service());
    }

    private static String compound(String account, String service) {
        return account + "@" + service;
    }

    private static void wipe(WindowsCredentialBackend.StoredCredential stored) {
        if (stored != null) Arrays.fill(stored.secret(), (byte) 0);
    }
}
