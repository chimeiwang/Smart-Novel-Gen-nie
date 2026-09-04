package cn.inkforge.cli.config;

import java.util.function.Supplier;

/** 将原生库加载失败归一化，避免输出平台路径或后端异常细节。 */
final class NativeCredentialLibraries {

    private NativeCredentialLibraries() {}

    static <T> T load(Supplier<T> loader) {
        try {
            return loader.get();
        } catch (LinkageError | RuntimeException exception) {
            throw new SecureCredentialBackendException("系统安全凭据后端不可用，请检查操作系统原生库");
        }
    }

    static <T> T access(Supplier<T> operation) {
        try {
            return operation.get();
        } catch (LinkageError | SecurityException exception) {
            throw new SecureCredentialBackendException("系统安全凭据后端不可用，请检查原生库和系统权限");
        }
    }

    static void perform(Runnable operation) {
        access(() -> {
            operation.run();
            return null;
        });
    }
}
