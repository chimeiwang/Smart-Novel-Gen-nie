package cn.inkforge.core.platform.db;

import java.sql.Array;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.ResultSetMetaData;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ArrayNode;
import tools.jackson.databind.node.ObjectNode;

/** 通过 PostgreSQL 系统目录在只读事务中采集结构，不执行建表或迁移。 */
public final class PostgresSchemaInspector {

    private static final ObjectMapper OBJECT_MAPPER = new ObjectMapper();

    private static final String TABLES_QUERY = """
            SELECT table_class.relname AS table_name
            FROM pg_catalog.pg_class AS table_class
            JOIN pg_catalog.pg_namespace AS namespace
              ON namespace.oid = table_class.relnamespace
            WHERE namespace.nspname = ?
              AND table_class.relkind = 'r'
            ORDER BY table_class.relname
            """;

    private static final String COLUMNS_QUERY = """
            SELECT
              table_class.relname AS table_name,
              attribute.attname AS column_name,
              pg_catalog.format_type(attribute.atttypid, attribute.atttypmod) AS format_type,
              type_info.typname AS udt_name,
              NOT attribute.attnotnull AS nullable,
              pg_catalog.pg_get_expr(default_info.adbin, default_info.adrelid) AS column_default
            FROM pg_catalog.pg_attribute AS attribute
            JOIN pg_catalog.pg_class AS table_class
              ON table_class.oid = attribute.attrelid
            JOIN pg_catalog.pg_namespace AS namespace
              ON namespace.oid = table_class.relnamespace
            JOIN pg_catalog.pg_type AS type_info
              ON type_info.oid = attribute.atttypid
            LEFT JOIN pg_catalog.pg_attrdef AS default_info
              ON default_info.adrelid = attribute.attrelid
             AND default_info.adnum = attribute.attnum
            WHERE namespace.nspname = ?
              AND table_class.relkind = 'r'
              AND attribute.attnum > 0
              AND NOT attribute.attisdropped
            ORDER BY table_class.relname, attribute.attnum
            """;

    private static final String PRIMARY_KEYS_QUERY = """
            SELECT
              table_class.relname AS table_name,
              constraint_info.conname AS constraint_name,
              key_position.ordinality AS position,
              attribute.attname AS column_name,
              constraint_info.condeferrable AS is_deferrable,
              constraint_info.condeferred AS is_deferred,
              constraint_info.convalidated AS is_validated
            FROM pg_catalog.pg_constraint AS constraint_info
            JOIN pg_catalog.pg_class AS table_class
              ON table_class.oid = constraint_info.conrelid
            JOIN pg_catalog.pg_namespace AS namespace
              ON namespace.oid = table_class.relnamespace
            JOIN LATERAL unnest(constraint_info.conkey) WITH ORDINALITY
              AS key_position(attnum, ordinality) ON true
            JOIN pg_catalog.pg_attribute AS attribute
              ON attribute.attrelid = table_class.oid
             AND attribute.attnum = key_position.attnum
            WHERE namespace.nspname = ?
              AND constraint_info.contype = 'p'
            ORDER BY table_class.relname, constraint_info.conname, key_position.ordinality
            """;

    private static final String FOREIGN_KEYS_QUERY = """
            SELECT
              source_table.relname AS table_name,
              constraint_info.conname AS constraint_name,
              key_position.ordinality AS position,
              source_attribute.attname AS column_name,
              target_namespace.nspname AS target_schema,
              target_table.relname AS target_table,
              target_attribute.attname AS target_column,
              CASE constraint_info.confupdtype
                WHEN 'a' THEN 'NO ACTION' WHEN 'r' THEN 'RESTRICT' WHEN 'c' THEN 'CASCADE'
                WHEN 'n' THEN 'SET NULL' WHEN 'd' THEN 'SET DEFAULT'
              END AS on_update,
              CASE constraint_info.confdeltype
                WHEN 'a' THEN 'NO ACTION' WHEN 'r' THEN 'RESTRICT' WHEN 'c' THEN 'CASCADE'
                WHEN 'n' THEN 'SET NULL' WHEN 'd' THEN 'SET DEFAULT'
              END AS on_delete,
              CASE constraint_info.confmatchtype
                WHEN 'f' THEN 'FULL' WHEN 'p' THEN 'PARTIAL' WHEN 's' THEN 'SIMPLE'
              END AS match_type,
              constraint_info.condeferrable AS is_deferrable,
              constraint_info.condeferred AS is_deferred,
              constraint_info.convalidated AS is_validated
            FROM pg_catalog.pg_constraint AS constraint_info
            JOIN pg_catalog.pg_class AS source_table
              ON source_table.oid = constraint_info.conrelid
            JOIN pg_catalog.pg_namespace AS source_namespace
              ON source_namespace.oid = source_table.relnamespace
            JOIN pg_catalog.pg_class AS target_table
              ON target_table.oid = constraint_info.confrelid
            JOIN pg_catalog.pg_namespace AS target_namespace
              ON target_namespace.oid = target_table.relnamespace
            JOIN LATERAL unnest(constraint_info.conkey, constraint_info.confkey)
              WITH ORDINALITY AS key_position(source_attnum, target_attnum, ordinality) ON true
            JOIN pg_catalog.pg_attribute AS source_attribute
              ON source_attribute.attrelid = source_table.oid
             AND source_attribute.attnum = key_position.source_attnum
            JOIN pg_catalog.pg_attribute AS target_attribute
              ON target_attribute.attrelid = target_table.oid
             AND target_attribute.attnum = key_position.target_attnum
            WHERE source_namespace.nspname = ?
              AND constraint_info.contype = 'f'
            ORDER BY source_table.relname, constraint_info.conname, key_position.ordinality
            """;

    private static final String UNIQUE_CONSTRAINTS_QUERY = """
            SELECT
              table_class.relname AS table_name,
              constraint_info.conname AS constraint_name,
              key_position.ordinality AS position,
              attribute.attname AS column_name,
              constraint_info.condeferrable AS is_deferrable,
              constraint_info.condeferred AS is_deferred,
              constraint_info.convalidated AS is_validated
            FROM pg_catalog.pg_constraint AS constraint_info
            JOIN pg_catalog.pg_class AS table_class
              ON table_class.oid = constraint_info.conrelid
            JOIN pg_catalog.pg_namespace AS namespace
              ON namespace.oid = table_class.relnamespace
            JOIN LATERAL unnest(constraint_info.conkey) WITH ORDINALITY
              AS key_position(attnum, ordinality) ON true
            JOIN pg_catalog.pg_attribute AS attribute
              ON attribute.attrelid = table_class.oid
             AND attribute.attnum = key_position.attnum
            WHERE namespace.nspname = ?
              AND constraint_info.contype = 'u'
            ORDER BY table_class.relname, constraint_info.conname, key_position.ordinality
            """;

    private static final String CHECK_CONSTRAINTS_QUERY = """
            SELECT
              table_class.relname AS table_name,
              constraint_info.conname AS constraint_name,
              pg_catalog.pg_get_constraintdef(constraint_info.oid, true) AS definition,
              constraint_info.convalidated AS is_validated,
              constraint_info.connoinherit AS no_inherit
            FROM pg_catalog.pg_constraint AS constraint_info
            JOIN pg_catalog.pg_class AS table_class
              ON table_class.oid = constraint_info.conrelid
            JOIN pg_catalog.pg_namespace AS namespace
              ON namespace.oid = table_class.relnamespace
            WHERE namespace.nspname = ?
              AND constraint_info.contype = 'c'
            ORDER BY table_class.relname, constraint_info.conname
            """;

    private static final String INDEXES_QUERY = """
            SELECT
              table_class.relname AS table_name,
              index_class.relname AS index_name,
              index_info.indisunique AS is_unique,
              access_method.amname AS method,
              key_position.position,
              key_position.position <= index_info.indnkeyatts AS is_key,
              indexed_attribute.attname AS column_name,
              CASE WHEN key_position.position <= index_info.indnkeyatts
                     AND indexed_attribute.attname IS NULL
                THEN pg_catalog.pg_get_indexdef(index_info.indexrelid, key_position.position, true)
                ELSE NULL
              END AS expression,
              opclass_namespace.nspname AS opclass_schema,
              opclass.opcname AS opclass_name,
              collation_namespace.nspname AS collation_schema,
              collation_info.collname AS collation_name,
              CASE WHEN ((index_info.indoption::smallint[])[key_position.position - 1] & 1) = 1
                THEN 'DESC' ELSE 'ASC'
              END AS order_direction,
              CASE WHEN ((index_info.indoption::smallint[])[key_position.position - 1] & 2) = 2
                THEN 'FIRST' ELSE 'LAST'
              END AS nulls_position,
              pg_catalog.pg_get_expr(index_info.indpred, index_info.indrelid) AS predicate,
              index_info.indisvalid AS is_valid,
              index_info.indisready AS is_ready,
              index_class.reloptions AS rel_options,
              tablespace.spcname AS tablespace_name,
              COALESCE(
                (pg_catalog.to_jsonb(index_info) ->> 'indnullsnotdistinct')::boolean,
                false
              ) AS nulls_not_distinct
            FROM pg_catalog.pg_index AS index_info
            JOIN pg_catalog.pg_class AS table_class
              ON table_class.oid = index_info.indrelid
            JOIN pg_catalog.pg_namespace AS namespace
              ON namespace.oid = table_class.relnamespace
            JOIN pg_catalog.pg_class AS index_class
              ON index_class.oid = index_info.indexrelid
            JOIN pg_catalog.pg_am AS access_method
              ON access_method.oid = index_class.relam
            JOIN LATERAL generate_series(1, index_info.indnatts) AS key_position(position) ON true
            LEFT JOIN pg_catalog.pg_attribute AS indexed_attribute
              ON indexed_attribute.attrelid = table_class.oid
             AND indexed_attribute.attnum = (index_info.indkey::smallint[])[key_position.position - 1]
            LEFT JOIN pg_catalog.pg_opclass AS opclass
              ON opclass.oid = (index_info.indclass::oid[])[key_position.position - 1]
             AND key_position.position <= index_info.indnkeyatts
            LEFT JOIN pg_catalog.pg_namespace AS opclass_namespace
              ON opclass_namespace.oid = opclass.opcnamespace
            LEFT JOIN pg_catalog.pg_collation AS collation_info
              ON collation_info.oid = (index_info.indcollation::oid[])[key_position.position - 1]
             AND key_position.position <= index_info.indnkeyatts
            LEFT JOIN pg_catalog.pg_namespace AS collation_namespace
              ON collation_namespace.oid = collation_info.collnamespace
            LEFT JOIN pg_catalog.pg_tablespace AS tablespace
              ON tablespace.oid = index_class.reltablespace
            WHERE namespace.nspname = ?
              AND table_class.relkind = 'r'
            ORDER BY table_class.relname, index_class.relname, key_position.position
            """;

    private static final String ENUMS_QUERY = """
            SELECT
              type_info.typname AS enum_name,
              enum_info.enumlabel AS enum_value,
              enum_info.enumsortorder AS sort_order
            FROM pg_catalog.pg_type AS type_info
            JOIN pg_catalog.pg_namespace AS namespace
              ON namespace.oid = type_info.typnamespace
            JOIN pg_catalog.pg_enum AS enum_info
              ON enum_info.enumtypid = type_info.oid
            WHERE namespace.nspname = ?
            ORDER BY type_info.typname, enum_info.enumsortorder
            """;

    private static final String EXTENSIONS_QUERY = """
            SELECT extension_info.extname AS extension_name, extension_info.extversion AS version
            FROM pg_catalog.pg_extension AS extension_info
            ORDER BY extension_info.extname
            """;

    /**
     * 在调用方提供的新连接上执行检查。为避免误提交业务写入，拒绝接管已经处于手工事务中的连接。
     */
    public SchemaContract inspect(Connection connection, String schema) throws SQLException {
        if (!connection.getAutoCommit()) {
            throw new IllegalArgumentException("结构检查只能使用未开启事务的新连接");
        }
        boolean originalReadOnly = connection.isReadOnly();
        connection.setReadOnly(true);
        connection.setAutoCommit(false);
        try {
            try (Statement statement = connection.createStatement()) {
                statement.execute("SET TRANSACTION READ ONLY");
                statement.execute("SET LOCAL search_path = pg_catalog, public");
            }
            return inspectWithinReadOnlyTransaction(connection, schema);
        } finally {
            connection.rollback();
            connection.setAutoCommit(true);
            connection.setReadOnly(originalReadOnly);
        }
    }

    private SchemaContract inspectWithinReadOnlyTransaction(Connection connection, String schema)
            throws SQLException {
        Map<String, ObjectNode> tables = new TreeMap<>();
        for (Row row : rows(connection, TABLES_QUERY, schema)) {
            String name = row.text("table_name");
            ObjectNode table = OBJECT_MAPPER.createObjectNode();
            table.put("name", name);
            table.putArray("columns");
            table.putNull("primaryKey");
            table.putArray("foreignKeys");
            table.putArray("uniqueConstraints");
            table.putArray("checkConstraints");
            table.putArray("indexes");
            tables.put(name, table);
        }

        inspectColumns(connection, schema, tables);
        inspectPrimaryKeys(connection, schema, tables);
        inspectForeignKeys(connection, schema, tables);
        inspectUniqueConstraints(connection, schema, tables);
        inspectCheckConstraints(connection, schema, tables);
        inspectIndexes(connection, schema, tables);

        ObjectNode document = OBJECT_MAPPER.createObjectNode();
        document.put("contractVersion", 2);
        document.put("schema", schema);
        ArrayNode tableArray = document.putArray("tables");
        tables.values().forEach(tableArray::add);
        document.set("enums", inspectEnums(connection, schema));
        document.set("extensions", inspectExtensions(connection));
        document.put("fingerprint", SchemaContract.canonicalFingerprint(document));
        return SchemaContract.load(document);
    }

    private void inspectColumns(Connection connection, String schema, Map<String, ObjectNode> tables)
            throws SQLException {
        for (Row row : rows(connection, COLUMNS_QUERY, schema)) {
            ObjectNode column = OBJECT_MAPPER.createObjectNode();
            column.put("name", row.text("column_name"));
            column.put("formatType", row.text("format_type"));
            column.put("udtName", row.text("udt_name"));
            column.put("nullable", row.bool("nullable"));
            putNullableText(column, "default", normalizeWhitespace(row.value("column_default")));
            table(tables, row).withArray("columns").add(column);
        }
        tables.values().forEach(table -> sortByName(table.withArray("columns")));
    }

    private void inspectPrimaryKeys(Connection connection, String schema, Map<String, ObjectNode> tables)
            throws SQLException {
        Map<String, ObjectNode> keys = new LinkedHashMap<>();
        for (Row row : rows(connection, PRIMARY_KEYS_QUERY, schema)) {
            String identity = identity(row);
            ObjectNode key = keys.computeIfAbsent(identity, ignored -> {
                ObjectNode created = OBJECT_MAPPER.createObjectNode();
                created.put("name", row.text("constraint_name"));
                created.putArray("columns");
                created.put("deferrable", row.bool("is_deferrable"));
                created.put("initiallyDeferred", row.bool("is_deferred"));
                created.put("validated", row.bool("is_validated"));
                return created;
            });
            key.withArray("columns").add(row.text("column_name"));
        }
        keys.forEach((identity, key) -> tables.get(tableName(identity)).set("primaryKey", key));
    }

    private void inspectForeignKeys(Connection connection, String schema, Map<String, ObjectNode> tables)
            throws SQLException {
        Map<String, ObjectNode> keys = new LinkedHashMap<>();
        for (Row row : rows(connection, FOREIGN_KEYS_QUERY, schema)) {
            String identity = identity(row);
            ObjectNode key = keys.computeIfAbsent(identity, ignored -> {
                ObjectNode created = OBJECT_MAPPER.createObjectNode();
                created.put("name", row.text("constraint_name"));
                created.putArray("columns");
                created.put("targetSchema", row.text("target_schema"));
                created.put("targetTable", row.text("target_table"));
                created.putArray("targetColumns");
                created.put("onUpdate", row.text("on_update"));
                created.put("onDelete", row.text("on_delete"));
                created.put("matchType", row.text("match_type"));
                created.put("deferrable", row.bool("is_deferrable"));
                created.put("initiallyDeferred", row.bool("is_deferred"));
                created.put("validated", row.bool("is_validated"));
                return created;
            });
            key.withArray("columns").add(row.text("column_name"));
            key.withArray("targetColumns").add(row.text("target_column"));
        }
        keys.forEach((identity, key) -> tables.get(tableName(identity)).withArray("foreignKeys").add(key));
        tables.values().forEach(table -> sortByName(table.withArray("foreignKeys")));
    }

    private void inspectUniqueConstraints(
            Connection connection, String schema, Map<String, ObjectNode> tables) throws SQLException {
        Map<String, ObjectNode> constraints = new LinkedHashMap<>();
        for (Row row : rows(connection, UNIQUE_CONSTRAINTS_QUERY, schema)) {
            String identity = identity(row);
            ObjectNode constraint = constraints.computeIfAbsent(identity, ignored -> {
                ObjectNode created = OBJECT_MAPPER.createObjectNode();
                created.put("name", row.text("constraint_name"));
                created.putArray("columns");
                created.put("deferrable", row.bool("is_deferrable"));
                created.put("initiallyDeferred", row.bool("is_deferred"));
                created.put("validated", row.bool("is_validated"));
                return created;
            });
            constraint.withArray("columns").add(row.text("column_name"));
        }
        constraints.forEach((identity, constraint) ->
                tables.get(tableName(identity)).withArray("uniqueConstraints").add(constraint));
        tables.values().forEach(table -> sortByName(table.withArray("uniqueConstraints")));
    }

    private void inspectCheckConstraints(
            Connection connection, String schema, Map<String, ObjectNode> tables) throws SQLException {
        for (Row row : rows(connection, CHECK_CONSTRAINTS_QUERY, schema)) {
            ObjectNode constraint = OBJECT_MAPPER.createObjectNode();
            constraint.put("name", row.text("constraint_name"));
            putNullableText(constraint, "definition", normalizeWhitespace(row.value("definition")));
            constraint.put("validated", row.bool("is_validated"));
            constraint.put("noInherit", row.bool("no_inherit"));
            table(tables, row).withArray("checkConstraints").add(constraint);
        }
        tables.values().forEach(table -> sortByName(table.withArray("checkConstraints")));
    }

    private void inspectIndexes(Connection connection, String schema, Map<String, ObjectNode> tables)
            throws SQLException {
        Map<String, ObjectNode> indexes = new LinkedHashMap<>();
        for (Row row : rows(connection, INDEXES_QUERY, schema)) {
            String identity = row.text("table_name") + '\u0000' + row.text("index_name");
            ObjectNode index = indexes.computeIfAbsent(identity, ignored -> {
                ObjectNode created = OBJECT_MAPPER.createObjectNode();
                created.put("name", row.text("index_name"));
                created.put("unique", row.bool("is_unique"));
                created.put("method", row.text("method"));
                created.putArray("keyItems");
                created.putArray("includeColumns");
                putNullableText(created, "predicate", normalizeWhitespace(row.value("predicate")));
                created.put("valid", row.bool("is_valid"));
                created.put("ready", row.bool("is_ready"));
                created.put("nullsNotDistinct", row.bool("nulls_not_distinct"));
                ArrayNode options = created.putArray("options");
                stringList(row.value("rel_options")).forEach(options::add);
                putNullableText(created, "tablespace", row.nullableText("tablespace_name"));
                return created;
            });
            if (row.bool("is_key")) {
                boolean expression = row.value("column_name") == null;
                ObjectNode item = OBJECT_MAPPER.createObjectNode();
                item.put("position", row.integer("position"));
                item.put("kind", expression ? "expression" : "column");
                putNullableText(item, "column", expression ? null : row.text("column_name"));
                putNullableText(item, "expression", expression ? row.text("expression") : null);
                putNullableText(item, "opclassSchema", row.nullableText("opclass_schema"));
                putNullableText(item, "opclass", row.nullableText("opclass_name"));
                putNullableText(item, "collationSchema", row.nullableText("collation_schema"));
                putNullableText(item, "collation", row.nullableText("collation_name"));
                item.put("order", row.text("order_direction"));
                item.put("nulls", row.text("nulls_position"));
                index.withArray("keyItems").add(item);
            } else {
                index.withArray("includeColumns").add(row.text("column_name"));
            }
        }
        indexes.forEach((identity, index) -> tables.get(tableName(identity)).withArray("indexes").add(index));
        tables.values().forEach(table -> sortByName(table.withArray("indexes")));
    }

    private ArrayNode inspectEnums(Connection connection, String schema) throws SQLException {
        Map<String, ArrayNode> enums = new TreeMap<>();
        for (Row row : rows(connection, ENUMS_QUERY, schema)) {
            enums.computeIfAbsent(row.text("enum_name"), ignored -> OBJECT_MAPPER.createArrayNode())
                    .add(row.text("enum_value"));
        }
        ArrayNode result = OBJECT_MAPPER.createArrayNode();
        enums.forEach((name, values) -> {
            ObjectNode enumType = OBJECT_MAPPER.createObjectNode();
            enumType.put("name", name);
            enumType.set("values", values);
            result.add(enumType);
        });
        return result;
    }

    private ArrayNode inspectExtensions(Connection connection) throws SQLException {
        ArrayNode result = OBJECT_MAPPER.createArrayNode();
        for (Row row : rows(connection, EXTENSIONS_QUERY, null)) {
            ObjectNode extension = OBJECT_MAPPER.createObjectNode();
            extension.put("name", row.text("extension_name"));
            extension.put("installed", true);
            extension.put("version", row.text("version"));
            result.add(extension);
        }
        return result;
    }

    private static List<Row> rows(Connection connection, String query, String schema) throws SQLException {
        try (PreparedStatement statement = connection.prepareStatement(query)) {
            if (schema != null) {
                statement.setString(1, schema);
            }
            try (ResultSet result = statement.executeQuery()) {
                ResultSetMetaData metadata = result.getMetaData();
                List<Row> rows = new ArrayList<>();
                while (result.next()) {
                    Map<String, Object> values = new LinkedHashMap<>();
                    for (int index = 1; index <= metadata.getColumnCount(); index++) {
                        values.put(metadata.getColumnLabel(index), result.getObject(index));
                    }
                    rows.add(new Row(values));
                }
                return rows;
            }
        }
    }

    private static ObjectNode table(Map<String, ObjectNode> tables, Row row) {
        ObjectNode table = tables.get(row.text("table_name"));
        if (table == null) {
            throw new IllegalStateException("系统目录返回了未知表：" + row.text("table_name"));
        }
        return table;
    }

    private static String identity(Row row) {
        return row.text("table_name") + '\u0000' + row.text("constraint_name");
    }

    private static String tableName(String identity) {
        return identity.substring(0, identity.indexOf('\u0000'));
    }

    private static void sortByName(ArrayNode array) {
        List<JsonNode> values = new ArrayList<>();
        array.forEach(values::add);
        values.sort(Comparator.comparing(node -> node.path("name").asString()));
        array.removeAll();
        values.forEach(array::add);
    }

    private static String normalizeWhitespace(Object value) {
        return value == null ? null : value.toString().replaceAll("\\s+", " ").trim();
    }

    private static void putNullableText(ObjectNode node, String name, String value) {
        if (value == null) {
            node.putNull(name);
        } else {
            node.put(name, value);
        }
    }

    private static List<String> stringList(Object value) {
        if (value == null) {
            return List.of();
        }
        Object raw;
        try {
            raw = value instanceof Array sqlArray ? sqlArray.getArray() : value;
        } catch (SQLException exception) {
            throw new IllegalStateException("无法读取 PostgreSQL 数组字段", exception);
        }
        if (!(raw instanceof Object[] items)) {
            throw new IllegalArgumentException("PostgreSQL 数组字段不是对象数组");
        }
        return Arrays.stream(items).map(String::valueOf).sorted().toList();
    }

    private record Row(Map<String, Object> values) {

        private Object value(String name) {
            return values.get(name);
        }

        private String text(String name) {
            Object value = values.get(name);
            if (value == null) {
                throw new IllegalStateException("系统目录字段不能为空：" + name);
            }
            return value.toString();
        }

        private String nullableText(String name) {
            Object value = values.get(name);
            return value == null ? null : value.toString();
        }

        private boolean bool(String name) {
            Object value = values.get(name);
            if (value instanceof Boolean booleanValue) {
                return booleanValue;
            }
            return Boolean.parseBoolean(text(name));
        }

        private int integer(String name) {
            Object value = values.get(name);
            if (value instanceof Number number) {
                return number.intValue();
            }
            return Integer.parseInt(text(name));
        }
    }
}
