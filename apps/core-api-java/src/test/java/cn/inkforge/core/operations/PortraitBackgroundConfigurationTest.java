package cn.inkforge.core.operations;

import static org.assertj.core.api.Assertions.assertThat;

import java.lang.reflect.Method;
import java.util.Arrays;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.SmartInitializingSingleton;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;

class PortraitBackgroundConfigurationTest {

    @Test
    void 画像后台启动器不得依赖调度器Bean的配置扫描顺序() {
        assertThat(PortraitBackgroundConfiguration.class
                        .isAnnotationPresent(ConditionalOnBean.class))
                .isFalse();
        Method factory = Arrays.stream(PortraitBackgroundConfiguration.class.getDeclaredMethods())
                .filter(method -> method.getReturnType().equals(SmartInitializingSingleton.class))
                .findFirst()
                .orElseThrow();
        assertThat(factory.getParameterTypes()).contains(ObjectProvider.class);
    }
}
