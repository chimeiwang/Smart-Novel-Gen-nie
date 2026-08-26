package cn.inkforge.cli.config;

import java.util.Locale;

/** 只选择已审核的系统安全存储，绝不回退到明文文件。 */
public final class PlatformCredentialStores {

    private PlatformCredentialStores() {}

    public static CredentialStore create(String operatingSystem) {
        String normalized = operatingSystem == null
                ? ""
                : operatingSystem.toLowerCase(Locale.ROOT);
        if (normalized.contains("mac") || normalized.contains("darwin")) {
            return new MacKeychainCredentialStore();
        }
        if (normalized.contains("win")) return new WindowsCredentialStore();
        throw new SecureCredentialBackendException(
                "生产 CLI 仅支持 macOS Keychain 或 Windows Credential Manager");
    }
}
