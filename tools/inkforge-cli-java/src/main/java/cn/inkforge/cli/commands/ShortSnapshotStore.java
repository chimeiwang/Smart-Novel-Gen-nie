package cn.inkforge.cli.commands;

import cn.inkforge.cli.runtime.CliInputException;
import cn.inkforge.cli.runtime.LocalFileException;
import cn.inkforge.cli.runtime.StableJson;
import cn.inkforge.cli.transport.AtomicFiles;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.Set;
import java.util.regex.Pattern;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ObjectNode;

/** 中短篇本地工作区的唯一文件边界，负责可信绑定、脏文件门禁与原子清单推进。 */
final class ShortSnapshotStore {

    private static final Pattern SHA256 = Pattern.compile("[0-9a-f]{64}");
    private static final Set<String> PROTECTED_MANIFEST_FIELDS =
            Set.of("schemaVersion", "novelId", "documents");
    private final ObjectMapper json;

    ShortSnapshotStore(ObjectMapper json) {
        this.json = json;
    }

    ObjectNode load(Path source, String novelId) {
        Path manifestPath = resolve(source);
        if (!manifestPath.getFileName().toString().equals("manifest.json")) {
            throw local("快照清单必须命名为 manifest.json");
        }
        JsonNode parsed;
        try {
            parsed = json.readTree(readUtf8(manifestPath));
        } catch (RuntimeException exception) {
            throw new LocalFileException("manifest.json 不可读或格式无效", exception);
        }
        if (!(parsed instanceof ObjectNode manifest)) {
            throw local("manifest.json 顶层必须是对象");
        }
        if (novelId != null && !textEquals(manifest, "novelId", novelId)) {
            throw local("manifest.json 与目标作品不匹配");
        }
        JsonNode documentsNode = manifest.get("documents");
        if (!(documentsNode instanceof ObjectNode documents)) {
            throw local("manifest.json 缺少 documents");
        }
        Path root = manifestPath.getParent();
        verifyDocument(documents, "outline", root.resolve("outline.md"));
        verifyDocument(documents, "manuscript", root.resolve("manuscript.txt"));
        return manifest;
    }

    ObjectNode ensureClean(Path source, String novelId) {
        Path manifestPath = resolve(source);
        ObjectNode manifest = load(manifestPath, novelId);
        ObjectNode documents = (ObjectNode) manifest.get("documents");
        Path root = manifestPath.getParent();
        ensureDocumentClean(documents, "outline", root.resolve("outline.md"));
        ensureDocumentClean(documents, "manuscript", root.resolve("manuscript.txt"));
        return manifest;
    }

    ObjectNode requireCleanManifest(ObjectNode payload, String novelId) {
        JsonNode raw = payload.get("manifestPath");
        if (raw == null || !raw.isTextual() || raw.textValue().isEmpty()) {
            throw new CliInputException(
                    "MANIFEST_REQUIRED",
                    "写操作必须提供 short.pull 生成的 manifestPath");
        }
        return ensureClean(Path.of(raw.textValue()), novelId);
    }

    ObjectNode export(
            Path directory,
            String novelId,
            String outline,
            String manuscript,
            ObjectNode metadata) {
        Path root = resolve(directory);
        Path manifestPath = root.resolve("manifest.json");
        Path outlinePath = root.resolve("outline.md");
        Path manuscriptPath = root.resolve("manuscript.txt");
        if (Files.exists(manifestPath)) {
            ensureClean(manifestPath, novelId);
        } else if (Files.exists(outlinePath) || Files.exists(manuscriptPath)) {
            throw local("目标目录已有文稿但缺少 manifest.json，拒绝覆盖");
        }

        writeUtf8(outlinePath, outline);
        writeUtf8(manuscriptPath, manuscript);
        String outlineHash = hash(outline.getBytes(StandardCharsets.UTF_8));
        String manuscriptHash = hash(manuscript.getBytes(StandardCharsets.UTF_8));

        ObjectNode manifest = json.createObjectNode();
        manifest.put("schemaVersion", 1);
        manifest.put("novelId", novelId);
        metadata.properties().forEach(entry -> {
            if (!PROTECTED_MANIFEST_FIELDS.contains(entry.getKey())) {
                manifest.set(entry.getKey(), entry.getValue().deepCopy());
            }
        });
        ObjectNode documents = manifest.putObject("documents");
        documentDescriptor(documents.putObject("outline"), outlinePath, outlineHash);
        documentDescriptor(documents.putObject("manuscript"), manuscriptPath, manuscriptHash);
        writeManifest(manifestPath, manifest);

        ObjectNode result = json.createObjectNode();
        result.put("manifestPath", manifestPath.toString());
        result.put("outlinePath", outlinePath.toString());
        result.put("manuscriptPath", manuscriptPath.toString());
        result.put("outlineContentHash", outlineHash);
        result.put("manuscriptContentHash", manuscriptHash);
        return result;
    }

    String advance(
            Path manifestSource,
            ObjectNode manifest,
            String documentType,
            String updatedAtField,
            String nextUpdatedAt,
            String content) {
        String contentHash = hash(content.getBytes(StandardCharsets.UTF_8));
        manifest.put(updatedAtField, nextUpdatedAt);
        ObjectNode documents = (ObjectNode) manifest.get("documents");
        ObjectNode descriptor = (ObjectNode) documents.get(documentType);
        descriptor.put("contentHash", contentHash);
        writeManifest(resolve(manifestSource), manifest);
        return contentHash;
    }

    String readUtf8(Path source) {
        byte[] bytes;
        try {
            bytes = Files.readAllBytes(resolve(source));
        } catch (IOException exception) {
            throw new LocalFileException("本地文件读取失败", exception);
        }
        try {
            return StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(bytes))
                    .toString();
        } catch (CharacterCodingException exception) {
            throw new LocalFileException("本地文件不是有效 UTF-8", exception);
        }
    }

    static String hash(byte[] value) {
        try {
            return HexFormat.of().formatHex(
                    MessageDigest.getInstance("SHA-256").digest(value));
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("当前 JRE 缺少 SHA-256", exception);
        }
    }

    private void verifyDocument(
            ObjectNode documents, String name, Path expectedSource) {
        JsonNode raw = documents.get(name);
        if (!(raw instanceof ObjectNode descriptor)) {
            throw local("manifest.json 缺少 " + name + " 文档描述");
        }
        Path expected = resolve(expectedSource);
        JsonNode path = descriptor.get("path");
        if (path == null
                || !path.isTextual()
                || !path.textValue().equals(expected.toString())) {
            throw local(name + " 路径必须精确等于快照目录中的 " + expected.getFileName());
        }
        JsonNode contentHash = descriptor.get("contentHash");
        if (contentHash == null
                || !contentHash.isTextual()
                || !SHA256.matcher(contentHash.textValue()).matches()) {
            throw local(name + " contentHash 不是小写 SHA-256");
        }
        if (!Files.isRegularFile(expected)) {
            throw local("快照缺少 " + expected.getFileName());
        }
    }

    private void ensureDocumentClean(
            ObjectNode documents, String name, Path documentSource) {
        ObjectNode descriptor = (ObjectNode) documents.get(name);
        byte[] bytes;
        try {
            bytes = Files.readAllBytes(resolve(documentSource));
        } catch (IOException exception) {
            throw new LocalFileException("快照文档读取失败", exception);
        }
        if (!hash(bytes).equals(descriptor.get("contentHash").textValue())) {
            throw local(name + " 存在尚未同步的本地修改，拒绝继续");
        }
    }

    private void writeManifest(Path target, ObjectNode manifest) {
        try {
            writeBytes(
                    target,
                    StableJson.pretty(json, manifest).getBytes(StandardCharsets.UTF_8));
        } catch (RuntimeException exception) {
            if (exception instanceof LocalFileException local) throw local;
            throw new LocalFileException("manifest.json 序列化失败", exception);
        }
    }

    private void writeUtf8(Path target, String content) {
        writeBytes(target, content.getBytes(StandardCharsets.UTF_8));
    }

    private void writeBytes(Path target, byte[] bytes) {
        try {
            AtomicFiles.write(
                    resolve(target),
                    new ByteArrayInputStream(bytes),
                    "application/octet-stream");
        } catch (IOException exception) {
            throw new LocalFileException("本地文件原子写入失败", exception);
        }
    }

    private static void documentDescriptor(
            ObjectNode target, Path path, String contentHash) {
        target.put("path", resolve(path).toString());
        target.put("contentHash", contentHash);
    }

    private static boolean textEquals(ObjectNode value, String field, String expected) {
        JsonNode actual = value.get(field);
        return actual != null && actual.isTextual() && actual.textValue().equals(expected);
    }

    private static Path resolve(Path source) {
        return source.toAbsolutePath().normalize();
    }

    private static LocalFileException local(String message) {
        return new LocalFileException(message);
    }
}
