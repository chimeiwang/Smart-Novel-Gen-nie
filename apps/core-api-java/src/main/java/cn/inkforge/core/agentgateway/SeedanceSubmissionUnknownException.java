package cn.inkforge.core.agentgateway;

/** Seedance 创建可能已送达供应商；调用方必须进入对账流程，禁止自动重提。 */
public final class SeedanceSubmissionUnknownException extends RuntimeException {

    public SeedanceSubmissionUnknownException() {
        super("Seedance 创建结果未知");
    }
}
