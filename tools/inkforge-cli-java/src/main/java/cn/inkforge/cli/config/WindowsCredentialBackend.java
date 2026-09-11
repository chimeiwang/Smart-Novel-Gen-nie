package cn.inkforge.cli.config;

/** Windows Credential Manager 的最小系统调用边界。 */
interface WindowsCredentialBackend {

    StoredCredential get(String target);

    void set(String target, String account, byte[] secret);

    void delete(String target);

    record StoredCredential(String account, byte[] secret) {}
}
