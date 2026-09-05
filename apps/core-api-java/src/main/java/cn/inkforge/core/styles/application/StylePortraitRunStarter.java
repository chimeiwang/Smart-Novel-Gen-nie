package cn.inkforge.core.styles.application;

import cn.inkforge.core.styles.domain.PortraitSection;
import cn.inkforge.core.styles.domain.PortraitTaskSnapshot;

/** 原整套/单节画像新请求的 V1/V2 启动边界，不新增公开请求参数。 */
public interface StylePortraitRunStarter {
    PortraitTaskSnapshot start(String userId, String styleId, PortraitSection section);
}
