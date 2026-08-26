package cn.inkforge.cli.registry;

import java.util.Objects;

/** Python CLI registry 的语言中立能力投影。 */
public record CommandSpec(
        String name,
        String pythonHandler,
        InputMode inputMode,
        OutputMode outputMode,
        FileOutput fileOutput,
        boolean mutation,
        boolean requiresIdentity,
        boolean requiresClientRequestId) {

    public CommandSpec {
        if (name == null || name.isBlank() || !name.equals(name.trim())) {
            throw new IllegalArgumentException("命令名不能为空或包含首尾空白");
        }
        if (pythonHandler == null || pythonHandler.isBlank()) {
            throw new IllegalArgumentException("命令缺少 Python 基线处理器身份");
        }
        Objects.requireNonNull(inputMode, "命令输入模式不能为空");
        Objects.requireNonNull(outputMode, "命令输出模式不能为空");
        Objects.requireNonNull(fileOutput, "命令文件输出声明不能为空");
        if (outputMode == OutputMode.JSONL && fileOutput.kind() != FileOutputKind.NONE) {
            throw new IllegalArgumentException("流式命令不能声明文件输出");
        }
        if (mutation && !requiresIdentity) {
            throw new IllegalArgumentException("写命令必须要求身份");
        }
        if (requiresClientRequestId && !mutation) {
            throw new IllegalArgumentException("只读命令不能要求 clientRequestId");
        }
    }

    public enum InputMode {
        ARGV_TTY,
        JSON;

        static InputMode fromWire(String value) {
            return switch (value) {
                case "argv_tty" -> ARGV_TTY;
                case "json" -> JSON;
                default -> throw new IllegalArgumentException("命令输入模式无效");
            };
        }
    }

    public enum OutputMode {
        JSON,
        JSONL;

        static OutputMode fromWire(String value) {
            return switch (value) {
                case "json" -> JSON;
                case "jsonl" -> JSONL;
                default -> throw new IllegalArgumentException("命令输出模式无效");
            };
        }
    }

    public enum FileOutputKind {
        NONE,
        DATA_JSON,
        PRIMARY_TEXT;

        static FileOutputKind fromWire(String value) {
            return switch (value) {
                case "none" -> NONE;
                case "data_json" -> DATA_JSON;
                case "primary_text" -> PRIMARY_TEXT;
                default -> throw new IllegalArgumentException("命令文件输出类型无效");
            };
        }
    }

    public record FileOutput(FileOutputKind kind, String field, String mediaType) {

        public FileOutput {
            Objects.requireNonNull(kind, "命令文件输出类型不能为空");
            if (kind == FileOutputKind.PRIMARY_TEXT) {
                if (field == null || field.isBlank() || mediaType == null || mediaType.isBlank()) {
                    throw new IllegalArgumentException("主文本输出缺少字段或媒体类型");
                }
            } else if (field != null || mediaType != null) {
                throw new IllegalArgumentException("命令文件输出元数据与类型不匹配");
            }
        }
    }
}
