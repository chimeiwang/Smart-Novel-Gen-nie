package cn.inkforge.core.billing.application;

import java.time.OffsetDateTime;

public record LedgerSnapshot(
        String id,
        String type,
        long amountMicros,
        long balanceAfterMicros,
        String note,
        OffsetDateTime createdAt) {}
