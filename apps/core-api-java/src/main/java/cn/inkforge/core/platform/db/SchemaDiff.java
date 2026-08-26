package cn.inkforge.core.platform.db;

import tools.jackson.databind.JsonNode;

/** 一项可定位的数据库结构差异；缺失的一侧使用 {@code null}。 */
public record SchemaDiff(String path, JsonNode expected, JsonNode actual, String message) {}
