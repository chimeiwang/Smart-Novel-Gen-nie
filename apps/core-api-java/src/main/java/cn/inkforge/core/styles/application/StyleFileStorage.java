package cn.inkforge.core.styles.application;

import org.springframework.web.multipart.MultipartFile;

/** 文风服务可使用的受控文件端口。 */
public interface StyleFileStorage {

    StoredStyleFile save(String styleId, String referenceId, MultipartFile upload);

    String read(String databasePath);

    boolean delete(String databasePath);
}
