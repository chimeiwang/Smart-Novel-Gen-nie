package cn.inkforge.cli.commands;

import cn.inkforge.cli.runtime.CliInputException;
import cn.inkforge.cli.runtime.CommandContext;
import cn.inkforge.cli.runtime.LocalFileException;
import cn.inkforge.cli.runtime.StableJson;
import cn.inkforge.cli.transport.AtomicFiles;
import cn.inkforge.cli.transport.FileDescriptor;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ObjectNode;

/** 兼容中短篇既有文件描述符；新增长篇输出继续使用统一 bytes/sha256 契约。 */
final class ShortFileOutputs {

    private ShortFileOutputs() {}

    static JsonNode responseField(
            CommandContext context,
            ObjectNode payload,
            JsonNode response,
            String field,
            String defaultName) {
        if (!(response instanceof ObjectNode object) || !object.has(field)) return response;
        Path output = outputPath(payload, defaultName);
        JsonNode value = object.get(field);
        String content = value.isTextual()
                ? value.textValue()
                : StableJson.pretty(context.dependencies().json(), value);
        ObjectNode result = object.deepCopy();
        result.remove(field);
        result.set(field + "File", writeLegacy(context, output, content));
        return result;
    }

    static ObjectNode wholeJson(
            CommandContext context,
            ObjectNode payload,
            JsonNode response,
            String defaultName,
            String resultField) {
        Path output = outputPath(payload, defaultName);
        String content = StableJson.pretty(context.dependencies().json(), response);
        ObjectNode result = context.dependencies().json().createObjectNode();
        result.set(resultField, writeLegacy(context, output, content));
        return result;
    }

    private static Path outputPath(ObjectNode payload, String defaultName) {
        JsonNode outputFile = payload.get("outputFile");
        if (outputFile == null || outputFile.isNull()) {
            JsonNode directory = payload.get("outputDirectory");
            if (directory != null
                    && directory.isTextual()
                    && !directory.textValue().isEmpty()) {
                return Path.of(directory.textValue()).resolve(defaultName);
            }
        }
        if (outputFile == null
                || !outputFile.isTextual()
                || outputFile.textValue().isEmpty()) {
            throw new CliInputException(
                    "OUTPUT_FILE_REQUIRED",
                    "完整响应必须提供 outputFile 或 outputDirectory");
        }
        return Path.of(outputFile.textValue());
    }

    private static ObjectNode writeLegacy(
            CommandContext context, Path target, String content) {
        byte[] bytes = content.getBytes(StandardCharsets.UTF_8);
        try {
            FileDescriptor written = AtomicFiles.write(
                    target,
                    new ByteArrayInputStream(bytes),
                    "application/octet-stream");
            ObjectNode descriptor = context.dependencies().json().createObjectNode();
            descriptor.put("path", written.path());
            descriptor.put("contentHash", written.sha256());
            descriptor.put("byteLength", written.bytes());
            descriptor.put(
                    "charCount", content.codePointCount(0, content.length()));
            return descriptor;
        } catch (IOException exception) {
            throw new LocalFileException("输出文件写入失败", exception);
        }
    }
}
