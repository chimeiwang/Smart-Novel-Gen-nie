package cn.inkforge.core.billing.domain;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

class BillingPricingTest {

    @Test
    void 费用必须区分未缓存输入缓存输入和完整输出() {
        assertThat(BillingPricing.usageCostMicros(100, 40, 25))
                .isEqualTo(60 * 1_000L + 40 * 20L + 25 * 2_000L);
        assertThat(BillingPricing.usageCostMicros(-1, 99, -2)).isZero();
        assertThat(BillingPricing.usageCostMicros(10, 99, 0)).isEqualTo(200L);
    }

    @Test
    void 积分格式最多保留三位小数且视频请求前缀不泄露任务标识() {
        assertThat(BillingPricing.formatCreditMicros(1_000_000_000L)).isEqualTo("1000");
        assertThat(BillingPricing.formatCreditMicros(1_234_567L)).isEqualTo("1.234");
        assertThat(BillingPricing.formatCreditMicros(-20_000L)).isEqualTo("-0.02");
        assertThat(BillingPricing.videoRequestPrefix("task-sensitive-1"))
                .matches("video-task-[0-9a-f]{32}-")
                .doesNotContain("task-sensitive-1");
    }
}
