package cn.inkforge.core.styles.application;

import cn.inkforge.core.styles.domain.PortraitDispatchStatus;
import cn.inkforge.core.styles.domain.PortraitSection;

/** 文风模块投递画像任务到 Agent 的最小端口。 */
public interface PortraitRunSubmitter {

    PortraitDispatchStatus submit(
            String userId,
            String styleId,
            String taskId,
            String runId,
            PortraitSection section);
}
