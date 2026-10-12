package cn.inkforge.core.writing.application;

/** 新建 V2 Run 前实时核对 Agent execution manifest 的出站端口。 */
@FunctionalInterface
public interface DurableAgentExecutionReadiness {

    /** 返回当前 Agent 是否就绪且与 Core 的 execution manifest 精确一致。 */
    boolean check();
}
