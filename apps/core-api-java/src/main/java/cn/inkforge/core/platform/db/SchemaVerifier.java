package cn.inkforge.core.platform.db;

import java.sql.Connection;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.TreeSet;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ArrayNode;
import tools.jackson.databind.node.ObjectNode;

/** 将实时 PostgreSQL 结构与冻结契约逐字段比较。 */
public final class SchemaVerifier {

    private final List<SchemaContract> expectedContracts;
    private final PostgresSchemaInspector inspector;
    private final SchemaProfile profile;

    public SchemaVerifier(SchemaContract expected) {
        this(List.of(expected), SchemaProfile.FULL);
    }

    public SchemaVerifier(SchemaContract expected, SchemaProfile profile) {
        this(List.of(expected), profile);
    }

    /**
     * 兼容镜像只接受列出的完整契约之一。候选不会合并，也不会把新增结构解释为可忽略的 additive drift。
     */
    public SchemaVerifier(List<SchemaContract> expectedContracts, SchemaProfile profile) {
        this(expectedContracts, new PostgresSchemaInspector(), profile);
    }

    SchemaVerifier(
            SchemaContract expected, PostgresSchemaInspector inspector, SchemaProfile profile) {
        this(List.of(expected), inspector, profile);
    }

    SchemaVerifier(
            List<SchemaContract> expectedContracts,
            PostgresSchemaInspector inspector,
            SchemaProfile profile) {
        if (expectedContracts == null || expectedContracts.isEmpty()) {
            throw new IllegalArgumentException("数据库结构契约候选不能为空");
        }
        this.expectedContracts = expectedContracts.stream()
                .map(contract -> SchemaContractProjector.project(contract, profile))
                .toList();
        this.inspector = inspector;
        this.profile = profile;
    }

    public SchemaVerificationResult verify(Connection connection, String schema) throws SQLException {
        SchemaContract actual = SchemaContractProjector.project(inspector.inspect(connection, schema), profile);
        List<SchemaDiff> nearestDiffs = null;
        for (SchemaContract expected : expectedContracts) {
            List<SchemaDiff> diffs = compare(
                    structural(expected.document()), structural(actual.document()), "");
            if (diffs.isEmpty()) {
                return new SchemaVerificationResult(true, actual.fingerprint(), List.of());
            }
            if (nearestDiffs == null || diffs.size() < nearestDiffs.size()) {
                nearestDiffs = diffs;
            }
        }
        return new SchemaVerificationResult(
                false,
                actual.fingerprint(),
                nearestDiffs == null ? List.of() : List.copyOf(nearestDiffs));
    }

    private static ObjectNode structural(JsonNode document) {
        ObjectNode copy = document.deepCopy().asObject();
        copy.remove(List.of("fingerprint", "source"));
        return copy;
    }

    private static List<SchemaDiff> compare(JsonNode expected, JsonNode actual, String path) {
        List<SchemaDiff> diffs = new ArrayList<>();
        compareInto(diffs, expected, actual, path);
        diffs.sort((left, right) -> left.path().compareTo(right.path()));
        return diffs;
    }

    private static void compareInto(
            List<SchemaDiff> diffs, JsonNode expected, JsonNode actual, String path) {
        if (expected == null || actual == null) {
            if (expected != actual) {
                addDiff(diffs, path, expected, actual);
            }
            return;
        }
        if (expected.isObject() && actual.isObject()) {
            TreeSet<String> names = new TreeSet<>(expected.propertyNames());
            names.addAll(actual.propertyNames());
            for (String name : names) {
                compareInto(diffs, expected.get(name), actual.get(name), childPath(path, name));
            }
            return;
        }
        if (expected.isArray() && actual.isArray()) {
            compareArrays(diffs, expected.asArray(), actual.asArray(), path);
            return;
        }
        if (!expected.equals(actual)) {
            addDiff(diffs, path, expected, actual);
        }
    }

    private static void compareArrays(
            List<SchemaDiff> diffs, ArrayNode expected, ArrayNode actual, String path) {
        String identityField = identityField(expected, actual);
        if (identityField != null) {
            Map<String, JsonNode> expectedItems = indexed(expected, identityField);
            Map<String, JsonNode> actualItems = indexed(actual, identityField);
            TreeSet<String> identities = new TreeSet<>(expectedItems.keySet());
            identities.addAll(actualItems.keySet());
            for (String identity : identities) {
                compareInto(
                        diffs,
                        expectedItems.get(identity),
                        actualItems.get(identity),
                        childPath(path, identity));
            }
            return;
        }
        int maximum = Math.max(expected.size(), actual.size());
        for (int index = 0; index < maximum; index++) {
            JsonNode expectedItem = index < expected.size() ? expected.get(index) : null;
            JsonNode actualItem = index < actual.size() ? actual.get(index) : null;
            compareInto(diffs, expectedItem, actualItem, childPath(path, Integer.toString(index)));
        }
    }

    private static String identityField(ArrayNode expected, ArrayNode actual) {
        if (supportsIdentity(expected, actual, "name")) {
            return "name";
        }
        if (supportsIdentity(expected, actual, "position")) {
            return "position";
        }
        return null;
    }

    private static boolean supportsIdentity(ArrayNode expected, ArrayNode actual, String field) {
        if (expected.isEmpty() && actual.isEmpty()) {
            return false;
        }
        for (JsonNode item : expected) {
            if (!item.isObject() || !item.hasNonNull(field)) {
                return false;
            }
        }
        for (JsonNode item : actual) {
            if (!item.isObject() || !item.hasNonNull(field)) {
                return false;
            }
        }
        return true;
    }

    private static Map<String, JsonNode> indexed(ArrayNode array, String field) {
        Map<String, JsonNode> result = new TreeMap<>();
        for (JsonNode item : array) {
            result.put(item.path(field).asString(), item);
        }
        return result;
    }

    private static void addDiff(
            List<SchemaDiff> diffs, String path, JsonNode expected, JsonNode actual) {
        String message;
        if (expected == null) {
            message = "存在额外结构项：" + path;
        } else if (actual == null) {
            message = "缺少结构项：" + path;
        } else if (path.endsWith("formatType")
                && (expected.asString().toLowerCase().contains("vector")
                        || actual.asString().toLowerCase().contains("vector"))) {
            message = "向量或列类型不一致：" + path;
        } else {
            message = "结构字段不一致：" + path;
        }
        diffs.add(new SchemaDiff(path, copy(expected), copy(actual), message));
    }

    private static JsonNode copy(JsonNode value) {
        return value == null ? null : value.deepCopy();
    }

    private static String childPath(String parent, String child) {
        return parent.isEmpty() ? child : parent + "." + child;
    }
}
