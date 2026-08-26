package cn.inkforge.core.writing.infrastructure;

import cn.inkforge.core.outlines.application.OutlineRepository;
import cn.inkforge.core.writing.application.WritingForeshadowingReader;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;

/** 将大纲领域的伏笔 DTO 转为工具内部 JSON 对象。 */
final class RepositoryWritingForeshadowingReader implements WritingForeshadowingReader {

    private final OutlineRepository outlines;
    private final ObjectMapper json;

    RepositoryWritingForeshadowingReader(OutlineRepository outlines, ObjectMapper json) {
        this.outlines = Objects.requireNonNull(outlines);
        this.json = Objects.requireNonNull(json);
    }

    @Override
    public List<Map<String, Object>> list(String novelId, String userId) {
        return outlines.listForeshadowings(novelId, userId).stream()
                .map(value -> json.convertValue(
                        value, new TypeReference<Map<String, Object>>() {}))
                .toList();
    }
}
