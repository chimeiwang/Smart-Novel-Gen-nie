package cn.inkforge.core.billing.application;

public record UsagePair(UsageSnapshot total, UsageSnapshot monthly) {}
