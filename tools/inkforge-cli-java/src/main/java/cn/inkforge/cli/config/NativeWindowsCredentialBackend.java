package cn.inkforge.cli.config;

import com.sun.jna.Library;
import com.sun.jna.Memory;
import com.sun.jna.Native;
import com.sun.jna.Pointer;
import com.sun.jna.Structure;
import com.sun.jna.WString;
import com.sun.jna.ptr.PointerByReference;
import com.sun.jna.win32.W32APIOptions;
import java.util.Arrays;

/** Windows Credential Manager 的最小 Unicode 绑定。 */
final class NativeWindowsCredentialBackend implements WindowsCredentialBackend {

    private static final int CRED_TYPE_GENERIC = 1;
    private static final int CRED_PERSIST_ENTERPRISE = 3;
    private static final int ERROR_NOT_FOUND = 1168;
    private final WinCredentials api;

    NativeWindowsCredentialBackend() {
        this(Native.load("Advapi32", WinCredentials.class, W32APIOptions.UNICODE_OPTIONS));
    }

    NativeWindowsCredentialBackend(WinCredentials api) {
        this.api = api;
    }

    @Override
    public synchronized StoredCredential get(String target) {
        PointerByReference reference = new PointerByReference();
        if (!api.CredReadW(new WString(target), CRED_TYPE_GENERIC, 0, reference)) {
            int error = Native.getLastError();
            if (error == ERROR_NOT_FOUND) return null;
            throw failure("CredReadW", error);
        }
        Pointer pointer = reference.getValue();
        try {
            Credential credential = new Credential(pointer);
            byte[] secret = credential.CredentialBlob == null
                    ? new byte[0]
                    : credential.CredentialBlob.getByteArray(0, credential.CredentialBlobSize);
            String account = credential.UserName == null ? "" : credential.UserName.toString();
            return new StoredCredential(account, secret);
        } finally {
            api.CredFree(pointer);
        }
    }

    @Override
    public synchronized void set(String target, String account, byte[] secret) {
        byte[] copy = Arrays.copyOf(secret, secret.length);
        Memory memory = new Memory(Math.max(copy.length, 1));
        try {
            if (copy.length > 0) memory.write(0, copy, 0, copy.length);
            Credential credential = new Credential();
            credential.Flags = 0;
            credential.Type = CRED_TYPE_GENERIC;
            credential.TargetName = new WString(target);
            credential.Comment = new WString("Stored using InkForge CLI");
            credential.LastWritten = new FileTime();
            credential.CredentialBlobSize = copy.length;
            credential.CredentialBlob = memory;
            credential.Persist = CRED_PERSIST_ENTERPRISE;
            credential.AttributeCount = 0;
            credential.Attributes = Pointer.NULL;
            credential.TargetAlias = null;
            credential.UserName = new WString(account);
            credential.write();
            if (!api.CredWriteW(credential, 0)) {
                throw failure("CredWriteW", Native.getLastError());
            }
        } finally {
            memory.clear();
            Arrays.fill(copy, (byte) 0);
        }
    }

    @Override
    public synchronized void delete(String target) {
        if (api.CredDeleteW(new WString(target), CRED_TYPE_GENERIC, 0)) return;
        int error = Native.getLastError();
        if (error != ERROR_NOT_FOUND) throw failure("CredDeleteW", error);
    }

    private static IllegalStateException failure(String operation, int error) {
        return new IllegalStateException(
                "Windows Credential Manager 操作失败（" + operation + "，Win32=" + error + "）");
    }

    interface WinCredentials extends Library {

        boolean CredReadW(WString targetName, int type, int flags, PointerByReference credential);

        boolean CredWriteW(Credential credential, int flags);

        boolean CredDeleteW(WString targetName, int type, int flags);

        void CredFree(Pointer buffer);
    }

    @Structure.FieldOrder({"lowDateTime", "highDateTime"})
    public static final class FileTime extends Structure {
        public int lowDateTime;
        public int highDateTime;
    }

    @Structure.FieldOrder({
        "Flags",
        "Type",
        "TargetName",
        "Comment",
        "LastWritten",
        "CredentialBlobSize",
        "CredentialBlob",
        "Persist",
        "AttributeCount",
        "Attributes",
        "TargetAlias",
        "UserName"
    })
    public static final class Credential extends Structure {
        public int Flags;
        public int Type;
        public WString TargetName;
        public WString Comment;
        public FileTime LastWritten;
        public int CredentialBlobSize;
        public Pointer CredentialBlob;
        public int Persist;
        public int AttributeCount;
        public Pointer Attributes;
        public WString TargetAlias;
        public WString UserName;

        public Credential() {}

        public Credential(Pointer pointer) {
            super(pointer);
            read();
        }
    }
}
