package cn.inkforge.core.references.application;

/** 仅用于任何 Run 写入前发现的本地执行服务缺失，不能包装数据库或登记中途错误。 */
public final class RagIndexRegistrationUnavailable extends RuntimeException {
    public RagIndexRegistrationUnavailable() { super("RAG 耐久运行服务未装配"); }
}
