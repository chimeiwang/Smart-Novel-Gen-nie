package cn.inkforge.core.platform.db;

import java.io.InputStream;
import tools.jackson.databind.ObjectMapper;

/** 只从应用内冻结资源加载数据库结构契约，运行时不接受外部路径替换。 */
final class SchemaContracts {

    private SchemaContracts() {}

    static SchemaContract loadBundled() {
        try (InputStream input = SchemaContracts.class.getResourceAsStream("/db/schema-contract.json")) {
            if (input == null) {
                throw new IllegalStateException("应用缺少数据库结构契约");
            }
            return SchemaContract.load(new ObjectMapper().readTree(input));
        } catch (Exception exception) {
            throw new IllegalStateException("数据库结构契约无法加载", exception);
        }
    }
}
