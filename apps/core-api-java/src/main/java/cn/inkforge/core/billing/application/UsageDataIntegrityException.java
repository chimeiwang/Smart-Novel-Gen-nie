package cn.inkforge.core.billing.application;

/** 历史 TokenUsage 缺少任务查询所需的权威身份。 */
public final class UsageDataIntegrityException extends RuntimeException {
    public UsageDataIntegrityException(String usageId) {
        super("模型用量记录缺少请求或运行标识：" + usageId);
    }
}
