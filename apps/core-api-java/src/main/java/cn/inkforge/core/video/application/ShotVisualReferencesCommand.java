package cn.inkforge.core.video.application;

import java.util.List;

/** 以完整集合替换逐镜视觉参考的 CAS 命令。 */
public record ShotVisualReferencesCommand(
        int expectedRevision, List<ShotVisualReferenceSelection> references) {

    public ShotVisualReferencesCommand {
        references = List.copyOf(references);
    }
}
