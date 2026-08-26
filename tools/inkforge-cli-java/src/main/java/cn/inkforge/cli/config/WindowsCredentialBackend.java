package cn.inkforge.cli.config;

interface WindowsCredentialBackend {

    StoredCredential get(String target);

    void set(String target, String account, byte[] secret);

    void delete(String target);

    record StoredCredential(String account, byte[] secret) {}
}
