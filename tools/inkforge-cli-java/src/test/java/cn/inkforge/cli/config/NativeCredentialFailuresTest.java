package cn.inkforge.cli.config;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.sun.jna.Native;
import java.lang.reflect.Proxy;
import org.junit.jupiter.api.Test;

class NativeCredentialFailuresTest {

    @Test
    void 原生库加载错误不泄露后端异常且统一安全凭据错误() {
        for (Throwable failure : new Throwable[] {
            new UnsatisfiedLinkError("敏感原生路径"),
            new NoClassDefFoundError("敏感类路径"),
            new SecurityException("敏感权限路径")
        }) {
            assertThatThrownBy(() -> NativeCredentialLibraries.load(() -> {
                if (failure instanceof Error error) throw error;
                throw (RuntimeException) failure;
            }))
                    .isInstanceOf(SecureCredentialBackendException.class)
                    .hasMessage("系统安全凭据后端不可用，请检查操作系统原生库")
                    .hasNoCause();
        }
    }

    @Test
    void 延迟解析原生符号与权限错误也归一化() {
        assertThatThrownBy(() -> NativeCredentialLibraries.access(() -> {
            throw new UnsatisfiedLinkError("含敏感路径的原生符号错误");
        })).isInstanceOf(SecureCredentialBackendException.class)
                .hasMessageNotContaining("含敏感路径").hasNoCause();
        assertThatThrownBy(() -> NativeCredentialLibraries.perform(() -> {
            throw new SecurityException("含敏感路径的权限错误");
        })).isInstanceOf(SecureCredentialBackendException.class)
                .hasMessageNotContaining("含敏感路径").hasNoCause();
    }

    @Test
    void Keychain读取新增与删除错误均使用安全凭据错误类型() {
        NativeMacKeychainBackend.CoreFoundation foundation = value -> {};
        NativeMacKeychainBackend denied = new NativeMacKeychainBackend(
                macSecurity(-25293, -25293), foundation);
        assertThatThrownBy(() -> denied.get("测试服务", "测试账户"))
                .isInstanceOf(SecureCredentialBackendException.class)
                .hasMessageContaining("OSStatus=-25293");
        assertThatThrownBy(() -> denied.delete("测试服务", "测试账户"))
                .isInstanceOf(SecureCredentialBackendException.class);
        NativeMacKeychainBackend addDenied = new NativeMacKeychainBackend(
                macSecurity(-25300, -25293), foundation);
        assertThat(addDenied.get("测试服务", "测试账户")).isNull();
        assertThatThrownBy(() -> addDenied.set("测试服务", "测试账户", "合成测试凭据"))
                .isInstanceOf(SecureCredentialBackendException.class)
                .hasMessageNotContaining("合成测试凭据");
    }

    @Test
    void Windows读取写入与删除错误均使用安全凭据错误类型() {
        NativeWindowsCredentialBackend backend = new NativeWindowsCredentialBackend(
                (NativeWindowsCredentialBackend.WinCredentials) Proxy.newProxyInstance(
                        getClass().getClassLoader(),
                        new Class<?>[] {NativeWindowsCredentialBackend.WinCredentials.class},
                        (proxy, method, arguments) -> {
                            Native.setLastError(5);
                            return method.getReturnType() == boolean.class ? false : null;
                        }));
        assertThatThrownBy(() -> backend.get("测试服务"))
                .isInstanceOf(SecureCredentialBackendException.class)
                .hasMessageContaining("Win32=5");
        assertThatThrownBy(() -> backend.set("测试服务", "测试账户", new byte[] {1, 2}))
                .isInstanceOf(SecureCredentialBackendException.class);
        assertThatThrownBy(() -> backend.delete("测试服务"))
                .isInstanceOf(SecureCredentialBackendException.class);
    }

    private NativeMacKeychainBackend.Security macSecurity(int findStatus, int writeStatus) {
        return (NativeMacKeychainBackend.Security) Proxy.newProxyInstance(
                getClass().getClassLoader(),
                new Class<?>[] {NativeMacKeychainBackend.Security.class},
                (proxy, method, arguments) -> method.getName().equals("SecKeychainFindGenericPassword")
                        ? findStatus
                        : writeStatus);
    }
}
