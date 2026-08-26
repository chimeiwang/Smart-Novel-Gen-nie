package cn.inkforge.core.operations;

import cn.inkforge.core.operations.background.BackgroundTaskManager;
import cn.inkforge.core.operations.background.BackgroundWorker;
import cn.inkforge.core.references.application.RagIndexDispatcher;
import org.springframework.beans.factory.SmartInitializingSingleton;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/** Operations 单向托管参考资料索引后台循环，业务模块不反向依赖运行控制面。 */
@Configuration(proxyBeanMethods = false)
@ConditionalOnBean(RagIndexDispatcher.class)
class RagIndexBackgroundConfiguration {

    @Bean
    SmartInitializingSingleton ragIndexDispatcherStarter(
            BackgroundTaskManager tasks, RagIndexDispatcher dispatcher) {
        BackgroundWorker worker = new BackgroundWorker() {
            @Override
            public void run() throws Exception {
                dispatcher.run();
            }

            @Override
            public void requestStop() {
                dispatcher.requestStop();
            }
        };
        return () -> tasks.start("rag_index_dispatcher", worker);
    }
}
