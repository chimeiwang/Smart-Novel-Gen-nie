package cn.inkforge.core.writing.application;

import java.util.List;
import java.util.Map;

/** 读取工具访问伏笔正式事实的窄端口。 */
@FunctionalInterface
public interface WritingForeshadowingReader {

    List<Map<String, Object>> list(String novelId, String userId);
}
