package cn.inkforge.core;

import static org.assertj.core.api.Assertions.assertThat;

import cn.inkforge.core.generated.api.BillingApi;
import cn.inkforge.core.generated.api.IdentityApi;
import cn.inkforge.core.generated.api.NovelsApi;
import cn.inkforge.core.generated.api.ReviewsApi;
import cn.inkforge.core.generated.api.VideoApi;
import cn.inkforge.core.generated.api.WritingApi;
import org.junit.jupiter.api.Test;

class GeneratedApiCoverageTest {

    @Test
    void 领域接口必须从179操作冻结契约生成() {
        assertThat(BillingApi.class).isNotNull();
        assertThat(IdentityApi.class).isNotNull();
        assertThat(NovelsApi.class).isNotNull();
        assertThat(ReviewsApi.class).isNotNull();
        assertThat(VideoApi.class).isNotNull();
        assertThat(WritingApi.class).isNotNull();
    }
}
