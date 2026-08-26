package cn.inkforge.cli.config;

/** 当前操作系统没有获准的安全凭据后端。 */
public final class SecureCredentialBackendException extends RuntimeException {

    public SecureCredentialBackendException(String message) {
        super(message);
    }
}
