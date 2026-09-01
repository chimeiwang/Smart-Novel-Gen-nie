package cn.inkforge.core.workflows.infrastructure;

import cn.inkforge.core.platform.config.CoreSettings;
import cn.inkforge.core.workflows.catalog.ExecutionRegistry;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/** Catalog/Profile 只读取镜像内版本化资源，不依赖数据库结构，可在迁移前安全装配。 */
@Configuration(proxyBeanMethods = false)
class WorkflowCatalogConfiguration {

    @Bean
    ExecutionRegistry workflowExecutionRegistry(CoreSettings settings) {
        return ExecutionRegistry.loadClasspath(
                ExecutionRegistry.Environment.valueOf(settings.environment().name()));
    }
}
