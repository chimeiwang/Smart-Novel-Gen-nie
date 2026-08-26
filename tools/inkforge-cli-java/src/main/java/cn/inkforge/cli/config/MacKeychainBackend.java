package cn.inkforge.cli.config;

interface MacKeychainBackend {

    String get(String service, String account);

    void set(String service, String account, String secret);

    void delete(String service, String account);
}
