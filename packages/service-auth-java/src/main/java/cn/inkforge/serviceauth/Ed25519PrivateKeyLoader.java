package cn.inkforge.serviceauth;

import java.nio.file.Path;
import java.security.PrivateKey;

/** 对业务模块开放的最小私钥加载入口；文件类型、权限、大小和换页攻击防护由共享实现统一负责。 */
public final class Ed25519PrivateKeyLoader {

    private Ed25519PrivateKeyLoader() {}

    public static PrivateKey fromPkcs8File(Path path) {
        return ServiceKeyFiles.readPrivateKey(path);
    }
}
