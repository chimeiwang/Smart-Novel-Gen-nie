package cn.inkforge.core.styles.application;

/** 文风新建 V2 画像前的 Agent 就绪与执行契约核对端口。 */
@FunctionalInterface
public interface StylePortraitExecutionReadiness {
    boolean check();
}
