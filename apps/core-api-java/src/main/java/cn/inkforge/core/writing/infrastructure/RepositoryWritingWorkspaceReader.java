package cn.inkforge.core.writing.infrastructure;

import cn.inkforge.core.novels.application.NovelRepository;
import cn.inkforge.core.writing.application.WritingWorkspaceReader;
import java.util.Map;
import java.util.Objects;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;

/** 复用小说领域的 repeatable-read 工作区聚合，不在写作模块复制查询。 */
final class RepositoryWritingWorkspaceReader implements WritingWorkspaceReader {

    private final NovelRepository novels;
    private final ObjectMapper json;

    RepositoryWritingWorkspaceReader(NovelRepository novels, ObjectMapper json) {
        this.novels = Objects.requireNonNull(novels);
        this.json = Objects.requireNonNull(json);
    }

    @Override
    public Map<String, Object> read(String userId, String novelId, String chapterId) {
        return json.convertValue(
                novels.workspace(novelId, userId, chapterId),
                new TypeReference<Map<String, Object>>() {});
    }
}
