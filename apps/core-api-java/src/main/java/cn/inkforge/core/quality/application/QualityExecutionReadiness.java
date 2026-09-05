package cn.inkforge.core.quality.application;

/** 一致性终检新建 V2 Run 前的 Agent 就绪与执行契约核对端口。 */
@FunctionalInterface
public interface QualityExecutionReadiness {
    boolean check();
}
