package cn.inkforge.core.billing.application;

import java.util.List;

public record SummarySnapshot(
        String username, long balanceMicros, List<LedgerSnapshot> entries) {
    public SummarySnapshot {
        entries = List.copyOf(entries);
    }
}
