package cn.inkforge.cli.config;

/** macOS Keychain 的最小系统调用边界。 */
interface MacKeychainBackend {

    String get(String service, String account);

    void set(String service, String account, String secret);

    void delete(String service, String account);
}
