package cn.inkforge.core.billing.application;

import java.time.OffsetDateTime;
import java.util.List;

/** 模型授权读取与 PostgreSQL 短事务结算端口。 */
public interface BillingRepository {

    AuthorizationContext authorizationContext(String userId, String taskId, String novelId);

    Long balance(String userId);

    ChargeResult charge(ChargeUsage usage);

    SummarySnapshot summary(String userId);

    UsagePair usage(String userId, OffsetDateTime monthStart);

    List<TaskUsageCallSnapshot> taskUsage(String userId, String taskId);
}
