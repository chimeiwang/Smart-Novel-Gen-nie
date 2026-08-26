package cn.inkforge.core.platform.db;

import java.util.List;

/** 实时数据库结构检查结果。 */
public record SchemaVerificationResult(boolean ready, String fingerprint, List<SchemaDiff> diffs) {

    public SchemaVerificationResult {
        diffs = List.copyOf(diffs);
    }
}
