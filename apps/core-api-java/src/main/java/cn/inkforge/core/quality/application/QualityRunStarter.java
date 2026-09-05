package cn.inkforge.core.quality.application;

import cn.inkforge.contracts.api.RunQualityCheckRequest;
import cn.inkforge.contracts.api.RunQualityCheckResponse;

/** 质量检查的新运行按当前配置路由，既有幂等身份始终按原引擎重放。 */
public interface QualityRunStarter {
    RunQualityCheckResponse start(String userId, String checkId, RunQualityCheckRequest request);
}
