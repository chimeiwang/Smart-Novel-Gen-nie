package cn.inkforge.cli.config;

import com.sun.jna.Library;
import com.sun.jna.Native;
import com.sun.jna.Pointer;
import com.sun.jna.ptr.IntByReference;
import com.sun.jna.ptr.PointerByReference;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

/** Security.framework 的最小通用密码绑定。 */
final class NativeMacKeychainBackend implements MacKeychainBackend {

    private static final int SUCCESS = 0;
    private static final int ITEM_NOT_FOUND = -25300;

    private final Security security;
    private final CoreFoundation coreFoundation;

    NativeMacKeychainBackend() {
        this(
                Native.load("Security", Security.class),
                Native.load("CoreFoundation", CoreFoundation.class));
    }

    NativeMacKeychainBackend(Security security, CoreFoundation coreFoundation) {
        this.security = security;
        this.coreFoundation = coreFoundation;
    }

    @Override
    public synchronized String get(String service, String account) {
        Found found = find(service, account);
        if (found == null) return null;
        try {
            return new String(found.secret(), StandardCharsets.UTF_8);
        } finally {
            found.close(security, coreFoundation);
        }
    }

    @Override
    public synchronized void set(String service, String account, String secret) {
        byte[] serviceBytes = service.getBytes(StandardCharsets.UTF_8);
        byte[] accountBytes = account.getBytes(StandardCharsets.UTF_8);
        byte[] secretBytes = secret.getBytes(StandardCharsets.UTF_8);
        Found found = find(serviceBytes, accountBytes);
        try {
            if (found == null) {
                PointerByReference item = new PointerByReference();
                check(security.SecKeychainAddGenericPassword(
                        Pointer.NULL,
                        serviceBytes.length,
                        serviceBytes,
                        accountBytes.length,
                        accountBytes,
                        secretBytes.length,
                        secretBytes,
                        item));
                release(item.getValue());
            } else {
                check(security.SecKeychainItemModifyAttributesAndData(
                        found.item(), Pointer.NULL, secretBytes.length, secretBytes));
            }
        } finally {
            if (found != null) found.close(security, coreFoundation);
            Arrays.fill(secretBytes, (byte) 0);
        }
    }

    @Override
    public synchronized void delete(String service, String account) {
        Found found = find(service, account);
        if (found == null) return;
        try {
            check(security.SecKeychainItemDelete(found.item()));
        } finally {
            found.close(security, coreFoundation);
        }
    }

    private Found find(String service, String account) {
        return find(
                service.getBytes(StandardCharsets.UTF_8),
                account.getBytes(StandardCharsets.UTF_8));
    }

    private Found find(byte[] service, byte[] account) {
        IntByReference length = new IntByReference();
        PointerByReference data = new PointerByReference();
        PointerByReference item = new PointerByReference();
        int status = security.SecKeychainFindGenericPassword(
                Pointer.NULL,
                service.length,
                service,
                account.length,
                account,
                length,
                data,
                item);
        if (status == ITEM_NOT_FOUND) return null;
        check(status);
        Pointer password = data.getValue();
        byte[] secret = password == null
                ? new byte[0]
                : password.getByteArray(0, length.getValue());
        return new Found(secret, password, item.getValue());
    }

    private void release(Pointer item) {
        if (item != null) coreFoundation.CFRelease(item);
    }

    private static void check(int status) {
        if (status != SUCCESS) {
            throw new IllegalStateException("macOS Keychain 操作失败（OSStatus=" + status + "）");
        }
    }

    private record Found(byte[] secret, Pointer allocatedData, Pointer item) {

        void close(Security security, CoreFoundation coreFoundation) {
            try {
                if (allocatedData != null) {
                    security.SecKeychainItemFreeContent(Pointer.NULL, allocatedData);
                }
            } finally {
                Arrays.fill(secret, (byte) 0);
                if (item != null) coreFoundation.CFRelease(item);
            }
        }
    }

    interface Security extends Library {

        int SecKeychainFindGenericPassword(
                Pointer keychainOrArray,
                int serviceNameLength,
                byte[] serviceName,
                int accountNameLength,
                byte[] accountName,
                IntByReference passwordLength,
                PointerByReference passwordData,
                PointerByReference itemRef);

        int SecKeychainAddGenericPassword(
                Pointer keychain,
                int serviceNameLength,
                byte[] serviceName,
                int accountNameLength,
                byte[] accountName,
                int passwordLength,
                byte[] passwordData,
                PointerByReference itemRef);

        int SecKeychainItemModifyAttributesAndData(
                Pointer itemRef,
                Pointer attributes,
                int length,
                byte[] data);

        int SecKeychainItemDelete(Pointer itemRef);

        int SecKeychainItemFreeContent(Pointer attributes, Pointer data);
    }

    interface CoreFoundation extends Library {

        void CFRelease(Pointer value);
    }
}
