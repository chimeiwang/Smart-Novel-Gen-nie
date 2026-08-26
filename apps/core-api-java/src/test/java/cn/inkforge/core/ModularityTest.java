package cn.inkforge.core;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTest {

    @Test
    void 模块依赖必须保持可验证() {
        ApplicationModules.of(CoreApplication.class).verify();
    }
}
