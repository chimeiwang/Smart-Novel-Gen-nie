from __future__ import annotations

import hashlib
import json
import logging
import re
from collections.abc import Mapping
from math import isfinite
from typing import Any, Literal, cast
from urllib.parse import unquote, urlparse

import jsonschema_rs
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_openai import ChatOpenAI
from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI

from ..config import Settings
from .base import (
    ModelFinishReason,
    ModelInvalidToolCallCode,
    ModelStructuredOutputDiagnostic,
    ModelStructuredOutputRequest,
    ModelStructuredOutputRoute,
    ModelToolCall,
    ModelToolRecoveryCode,
    ModelTurnRequest,
    ModelTurnResult,
    ModelUsage,
    ProviderTransportError,
    ProviderTransportErrorCode,
)

_DEEPSEEK_OFFICIAL_HOST = "api.deepseek.com"
_DEEPSEEK_STANDARD_BASE_URL = "https://api.deepseek.com"
_DEEPSEEK_STRICT_BASE_URL = "https://api.deepseek.com/beta"
_DEEPSEEK_RESPONSES_MODEL = "deepseek-v4-flash"
_MAX_RECOVERY_CONTAINER_DEPTH = 128
_RESPONSES_SCHEMA_KEYWORDS = (
    "type",
    "properties",
    "required",
    "additionalProperties",
    "enum",
    "anyOf",
    "items",
    "$ref",
    "$defs",
)
_SINGLE_JSON_FENCE_PATTERN = re.compile(
    r"\A[ \t\r\n]*```json[ \t]*\r?\n(?P<body>[\s\S]*?)\r?\n```[ \t\r\n]*\Z"
)
_SCENE_ASSET_SERVER_OWNED_FIELDS = frozenset(
    {
        "settingId",
        "bindingScope",
        "modality",
        "keyframeRole",
        "assetId",
        "usedInBeats",
    }
)
StructuredOutputRecoveryCode = Literal[
    "unwrap_single_json_fence",
    "normalize_scene_asset_source_redundancy",
    "normalize_cinematography_azimuth",
    "normalize_cinematography_lighting_inheritance",
    "normalize_cinematography_no_fill_direction",
    "normalize_cinematography_fill_direction_alias",
    "normalize_cinematography_infeasible_continuous_cut",
    "normalize_cinematography_unsigned_magnitudes",
]
logger = logging.getLogger(__name__)


def _is_deepseek_model(model_name: str) -> bool:
    return model_name.strip().casefold().startswith("deepseek-")


def _is_canonical_official_deepseek_url(base_url: str) -> bool:
    """判断是否为可安全派生官方 DeepSeek 能力的规范根 URL。"""

    parsed = urlparse(base_url)
    try:
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme.lower() == "https"
        and parsed.hostname is not None
        and parsed.hostname.lower() == _DEEPSEEK_OFFICIAL_HOST
        and port is None
        and not parsed.query
        and not parsed.fragment
        and unquote(parsed.path) in {"", "/", "/v1", "/v1/"}
    )


def _is_official_deepseek_endpoint(base_url: str) -> bool:
    """只信任官方规范根 URL，不能把非规范地址误判为官方能力。"""

    return _is_canonical_official_deepseek_url(base_url)


def _resolve_deepseek_strict_base_url(settings: Settings) -> str | None:
    if settings.openai_strict_base_url is not None:
        return settings.openai_strict_base_url
    if not _is_deepseek_model(settings.openai_model):
        return None
    if _is_canonical_official_deepseek_url(settings.openai_base_url):
        # 官方普通地址可能带 /v1；strict 通道固定使用官方 /beta 根地址。
        return _DEEPSEEK_STRICT_BASE_URL
    return None


def normalize_finish_reason(value: object) -> ModelFinishReason:
    if not isinstance(value, str):
        return "unknown"
    aliases: dict[str, ModelFinishReason] = {
        "stop": "stop",
        "tool_calls": "tool_calls",
        "function_call": "tool_calls",
        "length": "length",
        "max_tokens": "length",
        "content_filter": "content_filter",
        "insufficient_system_resource": "insufficient_system_resource",
    }
    return aliases.get(value, "unknown")


def _raw_finish_reason(value: object) -> str | None:
    if value is None:
        return None
    return value if isinstance(value, str) else str(value)


def _invalid_tool_call_code(tool_call: Mapping[str, Any]) -> ModelInvalidToolCallCode:
    """仅用标准 JSON 解析和结构事实分类，不读取可能含参数正文的 error。"""

    arguments = tool_call.get("args")
    if isinstance(arguments, str):
        try:
            json.loads(arguments)
        except json.JSONDecodeError:
            return "json_decode_error"

    name = tool_call.get("name")
    if not isinstance(name, str) or not name.strip():
        return "missing_tool_name"
    return "unknown_invalid_tool_call"


def _argument_character_count(tool_call: Mapping[str, Any]) -> int:
    """仅返回原始 arguments 的字符数；非字符串参数不做序列化或回显。"""

    arguments = tool_call.get("args")
    return len(arguments) if isinstance(arguments, str) else 0


def _schema_sha256(schema: Mapping[str, Any]) -> str:
    """计算稳定 Schema 指纹；诊断中只保留摘要，不暴露结构正文。"""

    canonical = json.dumps(
        schema,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _compile_structured_output_schema(
    structured_output: ModelStructuredOutputRequest,
) -> jsonschema_rs.Validator:
    """在发起付费请求前编译调用方 Schema，编程错误不能消耗模型额度。"""

    try:
        return jsonschema_rs.validator_for(structured_output.jsonSchema)
    except ValueError as exc:
        raise ValueError("structuredOutput.jsonSchema 不是有效的 JSON Schema") from exc


def _copy_json_value(value: Any) -> Any:
    """复制保留的 JSON 值，避免供应商 wire 与本地权威 Schema 共享可变容器。"""

    if isinstance(value, Mapping):
        return {str(key): _copy_json_value(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_copy_json_value(child) for child in value]
    return value


def _project_responses_schema_node(value: object) -> bool | dict[str, Any]:
    """递归投影 DeepSeek Responses 支持的窄 Schema 方言。"""

    if isinstance(value, bool):
        return value
    if not isinstance(value, Mapping):
        # 原始 Schema 已在投影前完整编译；这里只做防御性降级，绝不扩充供应商关键词。
        return {}

    projected: dict[str, Any] = {}
    for keyword in _RESPONSES_SCHEMA_KEYWORDS:
        if keyword not in value:
            continue
        keyword_value = value[keyword]
        if keyword in {"properties", "$defs"}:
            if isinstance(keyword_value, Mapping):
                # 字段名和定义名是业务标识符，不是 Schema 关键词，必须原样保留。
                projected[keyword] = {
                    str(name): _project_responses_schema_node(child)
                    for name, child in keyword_value.items()
                }
            continue
        if keyword == "anyOf":
            if isinstance(keyword_value, list):
                projected[keyword] = [
                    _project_responses_schema_node(child) for child in keyword_value
                ]
            continue
        if keyword in {"items", "additionalProperties"}:
            if isinstance(keyword_value, list):
                projected[keyword] = [
                    _project_responses_schema_node(child) for child in keyword_value
                ]
            else:
                projected[keyword] = _project_responses_schema_node(keyword_value)
            continue
        projected[keyword] = _copy_json_value(keyword_value)
    return projected


def _project_responses_schema(schema: Mapping[str, Any]) -> dict[str, Any]:
    """生成仅用于供应商提示的弱约束副本；本地复验仍使用原始完整 Schema。"""

    projected = _project_responses_schema_node(schema)
    if isinstance(projected, bool):
        # ModelStructuredOutputRequest 的根 Schema 固定为对象；此分支只用于静态类型收窄。
        return {}
    return projected


def _compile_responses_wire_schema(
    structured_output: ModelStructuredOutputRequest,
) -> dict[str, Any]:
    """独立编译供应商投影，不能把原始 Schema 已通过误当成 wire 也有效。"""

    wire_schema = _project_responses_schema(structured_output.jsonSchema)
    try:
        jsonschema_rs.validator_for(wire_schema)
    except ValueError:
        raise ValueError("Responses wire Schema 投影无效") from None
    return wire_schema


def _structured_schema_audit_fields(
    structured_output: ModelStructuredOutputRequest,
) -> dict[str, str | None]:
    """分别标识本地验证 Schema 与供应商 wire Schema，避免审计语义混淆。"""

    validation_hash = _schema_sha256(structured_output.jsonSchema)
    wire_hash = (
        _schema_sha256(_project_responses_schema(structured_output.jsonSchema))
        if structured_output.route == "responses_json_schema_v1"
        else None
    )
    return {
        # 兼容已有审计消费者；该字段始终代表本地权威验证 Schema。
        "schema_sha256": validation_hash,
        "validation_schema_sha256": validation_hash,
        "wire_schema_sha256": wire_hash,
    }


def _collect_known_property_names(value: object) -> set[str]:
    """收集 Schema 明示字段名，供错误路径脱敏，绝不读取模型未知字段名。"""

    known: set[str] = set()

    def visit(node: object) -> None:
        if isinstance(node, Mapping):
            properties = node.get("properties")
            if isinstance(properties, Mapping):
                known.update(str(name) for name in properties)
            for child in node.values():
                visit(child)
        elif isinstance(node, list):
            for child in node:
                visit(child)

    visit(value)
    return known


def _resolve_schema_path(schema: Mapping[str, Any], path: list[object]) -> object | None:
    """按 jsonschema-rs 的 schema_path 查找节点，仅用于确认 required 字段白名单。"""

    current: object = schema
    for segment in path:
        if isinstance(current, Mapping) and isinstance(segment, str):
            if segment not in current:
                return None
            current = current[segment]
        elif isinstance(current, list) and isinstance(segment, int):
            if segment < 0 or segment >= len(current):
                return None
            current = current[segment]
        else:
            return None
    return current


def _escape_json_pointer_segment(segment: object) -> str:
    """按 RFC 6901 转义已通过白名单的路径片段。"""

    return str(segment).replace("~", "~0").replace("/", "~1")


def _safe_schema_keyword(value: object) -> str:
    """Schema 关键字只允许固定安全字符，异常扩展名统一降为 unknown。"""

    if not isinstance(value, str) or not value or len(value) > 64:
        return "unknown"
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_$.-")
    return value if all(character in allowed for character in value) else "unknown"


def _validation_error_keyword(error: Any) -> str:
    """只读取 jsonschema-rs 的稳定关键字，不读取 message 或 instance。"""

    return _safe_schema_keyword(getattr(getattr(error, "kind", None), "name", None))


def _refine_any_of_validation_error(
    *,
    error: Any,
    schema: Mapping[str, Any],
    depth: int = 0,
) -> tuple[Any, list[object], Mapping[str, Any]]:
    """在内存中重验已知 anyOf 分支，只为安全诊断选择最接近的叶子错误。"""

    if depth >= 8 or _validation_error_keyword(error) != "anyOf":
        return error, [], schema
    raw_schema_path = list(getattr(error, "schema_path", []))
    branches = _resolve_schema_path(schema, raw_schema_path)
    if not isinstance(branches, list):
        return error, [], schema

    shared_definitions = schema.get("$defs")
    candidates: list[tuple[tuple[int, int, int], Any, dict[str, Any]]] = []
    for branch in branches:
        if not isinstance(branch, Mapping):
            continue
        candidate_schema: dict[str, Any] = {}
        if isinstance(shared_definitions, Mapping):
            candidate_schema["$defs"] = _copy_json_value(shared_definitions)
        candidate_schema.update(cast(dict[str, Any], _copy_json_value(branch)))
        try:
            validator = jsonschema_rs.validator_for(candidate_schema)
        except ValueError:
            continue
        branch_errors: list[Any] = []
        for branch_error in validator.iter_errors(getattr(error, "instance", None)):
            branch_errors.append(branch_error)
            if len(branch_errors) >= 64:
                break
        if not branch_errors:
            continue
        deepest_path = max(
            len(list(getattr(branch_error, "instance_path", []))) for branch_error in branch_errors
        )
        root_type_mismatch = any(
            _validation_error_keyword(branch_error) == "type"
            and not list(getattr(branch_error, "instance_path", []))
            for branch_error in branch_errors
        )
        # 先排除整个实例类型不匹配的分支，再选错误最少、路径最深的形状。
        score = (1 if root_type_mismatch else 0, len(branch_errors), -deepest_path)
        leaf_error = min(
            branch_errors,
            key=lambda item: (
                -len(list(getattr(item, "instance_path", []))),
                1 if _validation_error_keyword(item) == "anyOf" else 0,
            ),
        )
        candidates.append((score, leaf_error, candidate_schema))

    if not candidates:
        return error, [], schema
    _, selected_error, selected_schema = min(candidates, key=lambda item: item[0])
    refined_error, child_prefix, refined_schema = _refine_any_of_validation_error(
        error=selected_error,
        schema=selected_schema,
        depth=depth + 1,
    )
    parent_prefix = list(getattr(error, "instance_path", []))
    return refined_error, [*parent_prefix, *child_prefix], refined_schema


def _safe_validation_diagnostic(
    *,
    error: Any,
    schema: Mapping[str, Any],
) -> ModelStructuredOutputDiagnostic:
    """从 jsonschema-rs 错误派生白名单路径，禁止泄露字段值和未知字段名。"""

    known_property_names = _collect_known_property_names(schema)
    refined_error, path_prefix, refined_schema = _refine_any_of_validation_error(
        error=error,
        schema=schema,
    )
    raw_instance_path = [
        *path_prefix,
        *list(getattr(refined_error, "instance_path", [])),
    ]
    safe_segments: list[object] = []
    for segment in raw_instance_path:
        if isinstance(segment, int):
            safe_segments.append(segment)
        elif isinstance(segment, str) and segment in known_property_names:
            safe_segments.append(segment)
        else:
            # 一旦遇到 Schema 未声明的字段，路径停在已知父节点。
            break

    kind = getattr(refined_error, "kind", None)
    keyword = _safe_schema_keyword(getattr(kind, "name", None))
    if keyword == "required" and len(safe_segments) == len(raw_instance_path):
        missing_property = getattr(kind, "property", None)
        raw_schema_path = list(getattr(refined_error, "schema_path", []))
        parent_schema = _resolve_schema_path(refined_schema, raw_schema_path[:-1])
        parent_properties = (
            parent_schema.get("properties") if isinstance(parent_schema, Mapping) else None
        )
        if (
            isinstance(missing_property, str)
            and isinstance(parent_properties, Mapping)
            and missing_property in parent_properties
        ):
            # required 仅在缺失字段确属当前 Schema 对象时追加字段名。
            safe_segments.append(missing_property)

    pointer = "".join(f"/{_escape_json_pointer_segment(segment)}" for segment in safe_segments)
    return ModelStructuredOutputDiagnostic(
        code="schema_violation",
        jsonPointer=pointer,
        keyword=keyword,
    )


def _reject_nonstandard_json_constant(value: str) -> None:
    """拒绝 NaN/Infinity 等 Python json 默认接受但 JSON 标准不允许的常量。"""

    del value
    raise ValueError("结构化输出包含非标准 JSON 常量")


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """拒绝重复键，避免不同解析器对同一模型正文产生不同解释。"""

    parsed: dict[str, Any] = {}
    for key, value in pairs:
        if key in parsed:
            raise ValueError("结构化输出包含重复 JSON 键")
        parsed[key] = value
    return parsed


def _unwrap_single_json_fence(
    raw_text: str,
) -> tuple[str, StructuredOutputRecoveryCode | None]:
    """只解包占满整个输出且标记独占行的小写 json 围栏。"""

    match = _SINGLE_JSON_FENCE_PATTERN.fullmatch(raw_text)
    if match is None:
        return raw_text, None
    body = match.group("body")
    if "```" in body:
        return raw_text, None
    return body, "unwrap_single_json_fence"


def _normalize_scene_asset_source_redundancy(
    parsed: dict[str, Any],
    *,
    format_name: str,
) -> tuple[dict[str, Any], StructuredOutputRecoveryCode | None]:
    """移除素材阶段无创意含义的来源回显与服务器独占机械字段。"""

    if format_name != "video_scene_assets_draft_v1":
        return parsed, None
    raw_assets = parsed.get("assets")
    if not isinstance(raw_assets, dict):
        return parsed, None
    normalized = dict(parsed)
    normalized_assets = dict(raw_assets)
    changed = False
    for alias, raw_asset in raw_assets.items():
        if not isinstance(raw_asset, dict):
            continue
        normalized_asset = dict(raw_asset)
        asset_changed = False
        if raw_asset.get("sourceAlias") is not None and raw_asset.get("targetEntity") is not None:
            normalized_asset["targetEntity"] = None
            asset_changed = True
        for field in _SCENE_ASSET_SERVER_OWNED_FIELDS.intersection(raw_asset):
            normalized_asset.pop(field, None)
            asset_changed = True
        if asset_changed:
            normalized_assets[alias] = normalized_asset
            changed = True
    if not changed:
        return parsed, None
    normalized["assets"] = normalized_assets
    return normalized, "normalize_scene_asset_source_redundancy"


def _normalize_cinematography_azimuth(
    parsed: dict[str, Any],
    *,
    format_name: str,
) -> tuple[dict[str, Any], StructuredOutputRecoveryCode | None]:
    """把摄影机与灯位的圆周等价方位角归一到 -180..180。"""

    if format_name not in {
        "video_cinematography_draft_v1",
        "video_cinematography_draft_v2",
    }:
        return parsed, None

    def normalize_path(value: object, path: tuple[str, ...]) -> tuple[object, bool]:
        if not path:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return value, False
            if -180 <= value <= 180:
                return value, False
            normalized_angle = ((value + 180) % 360) - 180
            if isinstance(value, int):
                normalized_angle = int(normalized_angle)
            return normalized_angle, True
        if not isinstance(value, dict):
            return value, False
        key = path[0]
        if key not in value:
            return value, False
        normalized_child, changed = normalize_path(value[key], path[1:])
        if not changed:
            return value, False
        normalized_mapping = dict(value)
        normalized_mapping[key] = normalized_child
        return normalized_mapping, True

    def normalize_beat(raw_beat: object) -> tuple[object, bool]:
        normalized_beat = raw_beat
        changed = False
        for path in (
            ("cameraSpec", "position", "azimuthDegrees"),
            ("lightingCue", "keyLight", "azimuthDegrees"),
            ("lightingCue", "edgeLight", "azimuthDegrees"),
        ):
            normalized_beat, path_changed = normalize_path(normalized_beat, path)
            changed = changed or path_changed
        return normalized_beat, changed

    raw_beats = parsed.get("beats" if format_name.endswith("_v1") else "beatsByAlias")
    changed = False
    if isinstance(raw_beats, list):
        normalized_beats: object = []
        values = []
        for raw_beat in raw_beats:
            normalized_beat, beat_changed = normalize_beat(raw_beat)
            values.append(normalized_beat)
            changed = changed or beat_changed
        normalized_beats = values
        beats_key = "beats"
    elif isinstance(raw_beats, dict):
        values_by_alias: dict[str, object] = {}
        for alias, raw_beat in raw_beats.items():
            normalized_beat, beat_changed = normalize_beat(raw_beat)
            values_by_alias[alias] = normalized_beat
            changed = changed or beat_changed
        normalized_beats = values_by_alias
        beats_key = "beatsByAlias"
    else:
        return parsed, None
    if not changed:
        return parsed, None
    normalized = dict(parsed)
    normalized[beats_key] = normalized_beats
    return normalized, "normalize_cinematography_azimuth"


def _normalize_cinematography_lighting_inheritance(
    parsed: dict[str, Any],
    *,
    format_name: str,
) -> tuple[dict[str, Any], StructuredOutputRecoveryCode | None]:
    """把后续拍的旧继承表达归一为新协议的 JSON null。

    这里只恢复语义完全明确的继承，不猜测字符串 null，也不触碰首拍或变光参数。
    """

    if format_name != "video_cinematography_draft_v2":
        return parsed, None
    raw_beats = parsed.get("beatsByAlias")
    if not isinstance(raw_beats, dict):
        return parsed, None

    normalized_beats = dict(raw_beats)
    changed = False
    for alias, raw_beat in raw_beats.items():
        if alias == "B01" or not re.fullmatch(r"B\d{2}", alias):
            continue
        if not isinstance(raw_beat, dict):
            continue
        raw_lighting = raw_beat.get("lightingCue")
        uses_legacy_inheritance = raw_lighting == "__INHERIT__" or (
            isinstance(raw_lighting, Mapping) and raw_lighting.get("continuityMode") == "inherit"
        )
        if not uses_legacy_inheritance:
            continue
        normalized_beat = dict(raw_beat)
        normalized_beat["lightingCue"] = None
        normalized_beats[alias] = normalized_beat
        changed = True

    if not changed:
        return parsed, None
    normalized = dict(parsed)
    normalized["beatsByAlias"] = normalized_beats
    return normalized, "normalize_cinematography_lighting_inheritance"


def _normalize_cinematography_no_fill_direction(
    parsed: dict[str, Any],
    *,
    format_name: str,
) -> tuple[dict[str, Any], StructuredOutputRecoveryCode | None]:
    """以关闭策略为权威，丢弃无业务意义的补光方向与曝光占位。"""

    if format_name != "video_cinematography_draft_v2":
        return parsed, None
    raw_beats = parsed.get("beatsByAlias")
    if not isinstance(raw_beats, dict):
        return parsed, None

    normalized_beats = dict(raw_beats)
    changed = False
    for alias, raw_beat in raw_beats.items():
        if not re.fullmatch(r"B\d{2}", alias) or not isinstance(raw_beat, dict):
            continue
        raw_lighting = raw_beat.get("lightingCue")
        if not isinstance(raw_lighting, Mapping):
            continue
        relative_stops = raw_lighting.get("fillRelativeStops")
        raw_direction = raw_lighting.get("fillDirection")
        if (
            raw_lighting.get("fillStrategy") != "none"
            or not (raw_direction is None or isinstance(raw_direction, str))
            or isinstance(relative_stops, bool)
            or not isinstance(relative_stops, (int, float))
            or not isfinite(float(relative_stops))
            or not -8 <= relative_stops <= 8
        ):
            continue
        if raw_direction is None and relative_stops == -8:
            continue
        normalized_lighting = dict(raw_lighting)
        normalized_lighting["fillDirection"] = None
        normalized_lighting["fillRelativeStops"] = -8
        normalized_beat = dict(raw_beat)
        normalized_beat["lightingCue"] = normalized_lighting
        normalized_beats[alias] = normalized_beat
        changed = True

    if not changed:
        return parsed, None
    normalized = dict(parsed)
    normalized["beatsByAlias"] = normalized_beats
    return normalized, "normalize_cinematography_no_fill_direction"


def _normalize_cinematography_fill_direction_alias(
    parsed: dict[str, Any],
    *,
    format_name: str,
) -> tuple[dict[str, Any], StructuredOutputRecoveryCode | None]:
    """把补光槽误用的相邻机位侧别投影到 canonical 画面侧别。"""

    if format_name != "video_cinematography_draft_v2":
        return parsed, None
    raw_beats = parsed.get("beatsByAlias")
    if not isinstance(raw_beats, dict):
        return parsed, None

    direction_aliases = {
        "camera_left": "side_left",
        "camera_right": "side_right",
    }
    active_fill_strategies = {"soft_fill", "bounce_fill", "negative_fill"}
    normalized_beats = dict(raw_beats)
    changed = False
    for alias, raw_beat in raw_beats.items():
        if not re.fullmatch(r"B\d{2}", alias) or not isinstance(raw_beat, dict):
            continue
        raw_lighting = raw_beat.get("lightingCue")
        if not isinstance(raw_lighting, Mapping):
            continue
        if raw_lighting.get("fillStrategy") not in active_fill_strategies:
            continue
        raw_direction = raw_lighting.get("fillDirection")
        if not isinstance(raw_direction, str):
            continue
        canonical_direction = direction_aliases.get(raw_direction)
        if canonical_direction is None:
            continue
        normalized_lighting = dict(raw_lighting)
        normalized_lighting["fillDirection"] = canonical_direction
        normalized_beat = dict(raw_beat)
        normalized_beat["lightingCue"] = normalized_lighting
        normalized_beats[alias] = normalized_beat
        changed = True

    if not changed:
        return parsed, None
    normalized = dict(parsed)
    normalized["beatsByAlias"] = normalized_beats
    return normalized, "normalize_cinematography_fill_direction_alias"


def _normalize_cinematography_unsigned_magnitudes(
    parsed: dict[str, Any],
    *,
    format_name: str,
) -> tuple[dict[str, Any], StructuredOutputRecoveryCode | None]:
    """去掉无符号摄影量上多余的方向符号，不夹取越界数据。"""

    if format_name != "video_cinematography_draft_v2":
        return parsed, None

    def normalize_magnitude(value: object, maximum: float) -> tuple[object, bool]:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return value, False
        if value >= 0 or value < -maximum:
            return value, False
        return abs(value), True

    changed = False
    normalized = dict(parsed)
    raw_setup = parsed.get("lightingSetup")
    if isinstance(raw_setup, Mapping):
        normalized_gap, gap_changed = normalize_magnitude(
            raw_setup.get("keyToFillStops"),
            8,
        )
        if gap_changed:
            normalized_setup = dict(raw_setup)
            normalized_setup["keyToFillStops"] = normalized_gap
            normalized["lightingSetup"] = normalized_setup
            changed = True

    raw_beats = parsed.get("beatsByAlias")
    if isinstance(raw_beats, dict):
        normalized_beats = dict(raw_beats)
        for alias, raw_beat in raw_beats.items():
            if not re.fullmatch(r"B\d{2}", alias) or not isinstance(raw_beat, dict):
                continue
            raw_camera = raw_beat.get("cameraSpec")
            if not isinstance(raw_camera, Mapping):
                continue
            raw_movement = raw_camera.get("movement")
            if not isinstance(raw_movement, Mapping):
                continue
            normalized_distance, distance_changed = normalize_magnitude(
                raw_movement.get("travelDistanceMeters"),
                50,
            )
            normalized_rotation, rotation_changed = normalize_magnitude(
                raw_movement.get("rotationDegrees"),
                360,
            )
            if not distance_changed and not rotation_changed:
                continue
            normalized_movement = dict(raw_movement)
            if distance_changed:
                normalized_movement["travelDistanceMeters"] = normalized_distance
            if rotation_changed:
                normalized_movement["rotationDegrees"] = normalized_rotation
            normalized_camera = dict(raw_camera)
            normalized_camera["movement"] = normalized_movement
            normalized_beat = dict(raw_beat)
            normalized_beat["cameraSpec"] = normalized_camera
            normalized_beats[alias] = normalized_beat
            changed = True
        if normalized_beats != raw_beats:
            normalized["beatsByAlias"] = normalized_beats

    if not changed:
        return parsed, None
    return normalized, "normalize_cinematography_unsigned_magnitudes"


def _normalize_cinematography_infeasible_continuous_cut(
    parsed: dict[str, Any],
    *,
    format_name: str,
    validator: jsonschema_rs.Validator,
) -> tuple[dict[str, Any], StructuredOutputRecoveryCode | None]:
    """把唯一可证明不可执行的连续景别变化收敛为中性切镜。"""

    if format_name != "video_cinematography_draft_v2":
        return parsed, None
    if next(validator.iter_errors(parsed), None) is None:
        return parsed, None
    raw_beats = parsed.get("beatsByAlias")
    if not isinstance(raw_beats, dict):
        return parsed, None

    valid_candidates: list[dict[str, Any]] = []
    for alias, raw_beat in raw_beats.items():
        if not re.fullmatch(r"B\d{2}", alias) or not isinstance(raw_beat, dict):
            continue
        raw_progression = raw_beat.get("shotProgression")
        if not isinstance(raw_progression, Mapping):
            continue
        if raw_progression.get("changeMode") != "continuous":
            continue

        normalized_progression = dict(raw_progression)
        normalized_progression["changeMode"] = "cut"
        normalized_beat = dict(raw_beat)
        normalized_beat["shotProgression"] = normalized_progression
        normalized_beats = dict(raw_beats)
        normalized_beats[alias] = normalized_beat
        candidate = dict(parsed)
        candidate["beatsByAlias"] = normalized_beats
        if next(validator.iter_errors(candidate), None) is None:
            valid_candidates.append(candidate)

    if len(valid_candidates) != 1:
        return parsed, None
    return (
        valid_candidates[0],
        "normalize_cinematography_infeasible_continuous_cut",
    )


def _parse_and_validate_structured_output(
    *,
    raw_text: str,
    structured_output: ModelStructuredOutputRequest,
    validator: jsonschema_rs.Validator,
) -> tuple[
    dict[str, Any] | None,
    ModelStructuredOutputDiagnostic | None,
    StructuredOutputRecoveryCode | None,
]:
    """解析后立即本地复验；失败草稿只留在当前栈帧，不进入领域结果。"""

    if not raw_text.strip():
        return (
            None,
            ModelStructuredOutputDiagnostic(
                code="empty_output",
                jsonPointer="",
                keyword="content",
            ),
            None,
        )
    json_text, recovery_code = _unwrap_single_json_fence(raw_text)
    try:
        parsed = json.loads(
            json_text,
            parse_constant=_reject_nonstandard_json_constant,
            object_pairs_hook=_reject_duplicate_json_keys,
        )
    except (json.JSONDecodeError, ValueError):
        return (
            None,
            ModelStructuredOutputDiagnostic(
                code="json_decode_error",
                jsonPointer="",
                keyword="json",
            ),
            recovery_code,
        )
    if not isinstance(parsed, dict):
        return (
            None,
            ModelStructuredOutputDiagnostic(
                code="not_object",
                jsonPointer="",
                keyword="type",
            ),
            recovery_code,
        )
    parsed, redundancy_recovery = _normalize_scene_asset_source_redundancy(
        parsed,
        format_name=structured_output.name,
    )
    if redundancy_recovery:
        recovery_code = redundancy_recovery
    parsed, azimuth_recovery = _normalize_cinematography_azimuth(
        parsed,
        format_name=structured_output.name,
    )
    if azimuth_recovery:
        recovery_code = azimuth_recovery
    parsed, lighting_recovery = _normalize_cinematography_lighting_inheritance(
        parsed,
        format_name=structured_output.name,
    )
    if lighting_recovery:
        recovery_code = lighting_recovery
    parsed, no_fill_recovery = _normalize_cinematography_no_fill_direction(
        parsed,
        format_name=structured_output.name,
    )
    if no_fill_recovery:
        recovery_code = no_fill_recovery
    parsed, fill_direction_recovery = _normalize_cinematography_fill_direction_alias(
        parsed,
        format_name=structured_output.name,
    )
    if fill_direction_recovery:
        recovery_code = fill_direction_recovery
    parsed, magnitude_recovery = _normalize_cinematography_unsigned_magnitudes(
        parsed,
        format_name=structured_output.name,
    )
    if magnitude_recovery:
        recovery_code = magnitude_recovery
    parsed, progression_recovery = _normalize_cinematography_infeasible_continuous_cut(
        parsed,
        format_name=structured_output.name,
        validator=validator,
    )
    if progression_recovery:
        recovery_code = progression_recovery
    first_error = next(validator.iter_errors(parsed), None)
    if first_error is not None:
        return (
            None,
            _safe_validation_diagnostic(
                error=first_error,
                schema=structured_output.jsonSchema,
            ),
            recovery_code,
        )
    return parsed, None, recovery_code


def _usage_from_payload(payload: Mapping[str, Any], *, responses: bool) -> ModelUsage:
    """兼容 Responses、OpenAI Chat 与 DeepSeek 缓存命中字段。"""

    raw_usage = payload.get("usage")
    usage = raw_usage if isinstance(raw_usage, Mapping) else {}
    if responses:
        prompt_tokens = int(usage.get("input_tokens", 0) or 0)
        completion_tokens = int(usage.get("output_tokens", 0) or 0)
        details_value = usage.get("input_tokens_details")
    else:
        prompt_tokens = int(usage.get("prompt_tokens", 0) or 0)
        completion_tokens = int(usage.get("completion_tokens", 0) or 0)
        details_value = usage.get("prompt_tokens_details")
    details = details_value if isinstance(details_value, Mapping) else {}
    cached_tokens = int(
        details.get("cached_tokens", details.get("cache_read", 0))
        or usage.get("prompt_cache_hit_tokens", 0)
        or 0
    )
    total_tokens = int(
        usage.get("total_tokens", prompt_tokens + completion_tokens)
        or (prompt_tokens + completion_tokens)
    )
    return ModelUsage(
        promptTokens=prompt_tokens,
        cachedTokens=cached_tokens,
        completionTokens=completion_tokens,
        totalTokens=total_tokens,
    )


def _chat_message_payloads(request: ModelTurnRequest) -> list[dict[str, Any]]:
    """无损转换 Chat 消息，工具历史只作为既有上下文回传。"""

    payloads: list[dict[str, Any]] = []
    for message in request.messages:
        payload: dict[str, Any] = {
            "role": message.role,
            "content": message.content,
        }
        if message.name is not None:
            payload["name"] = message.name
        if message.role == "assistant" and message.tool_calls:
            payload["tool_calls"] = [
                {
                    "id": tool_call.id,
                    "type": "function",
                    "function": {
                        "name": tool_call.name,
                        "arguments": json.dumps(
                            tool_call.arguments,
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                    },
                }
                for tool_call in message.tool_calls
            ]
        if message.role == "tool":
            if message.tool_call_id is None:
                raise ValueError("工具消息缺少 toolCallId")
            payload["tool_call_id"] = message.tool_call_id
        payloads.append(payload)
    return payloads


def _responses_input_payloads(request: ModelTurnRequest) -> list[dict[str, Any]]:
    """把既有消息历史转换为 DeepSeek 无状态 Responses input items。"""

    payloads: list[dict[str, Any]] = []
    for message in request.messages:
        if message.role == "tool":
            if message.tool_call_id is None:
                raise ValueError("工具消息缺少 toolCallId")
            payloads.append(
                {
                    "type": "function_call_output",
                    "call_id": message.tool_call_id,
                    "output": message.content,
                }
            )
            continue
        if message.content or not message.tool_calls:
            payloads.append(
                {
                    "type": "message",
                    "role": message.role,
                    "content": message.content,
                }
            )
        if message.role == "assistant":
            payloads.extend(
                {
                    "type": "function_call",
                    "call_id": tool_call.id,
                    "name": tool_call.name,
                    "arguments": json.dumps(
                        tool_call.arguments,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                }
                for tool_call in message.tool_calls
            )
    return payloads


def _log_structured_output_diagnostic(
    *,
    model_name: str,
    structured_output: ModelStructuredOutputRequest,
    diagnostic: ModelStructuredOutputDiagnostic,
    usage: ModelUsage,
) -> None:
    """日志只记录安全诊断、Schema 指纹和用量，不记录供应商正文。"""

    logger.warning(
        "供应商结构化输出未通过本地验收 code=%s pointer=%s keyword=%s",
        diagnostic.code,
        json.dumps(diagnostic.jsonPointer, ensure_ascii=True),
        diagnostic.keyword,
        extra={
            "model_name": model_name,
            "structured_route": structured_output.route,
            "structured_code": diagnostic.code,
            "structured_json_pointer": diagnostic.jsonPointer,
            "structured_keyword": diagnostic.keyword,
            **_structured_schema_audit_fields(structured_output),
            "prompt_tokens": usage.promptTokens,
            "cached_tokens": usage.cachedTokens,
            "completion_tokens": usage.completionTokens,
            "total_tokens": usage.totalTokens,
        },
    )


def _log_structured_output_recovery(
    *,
    model_name: str,
    structured_output: ModelStructuredOutputRequest,
    recovery_code: StructuredOutputRecoveryCode,
    usage: ModelUsage,
) -> None:
    """记录确定性围栏解包；只暴露固定恢复码与安全审计元数据。"""

    logger.warning(
        "供应商结构化输出已执行确定性恢复 code=%s",
        recovery_code,
        extra={
            "model_name": model_name,
            "structured_route": structured_output.route,
            "structured_recovery_code": recovery_code,
            **_structured_schema_audit_fields(structured_output),
            "prompt_tokens": usage.promptTokens,
            "cached_tokens": usage.cachedTokens,
            "completion_tokens": usage.completionTokens,
            "total_tokens": usage.totalTokens,
        },
    )


def _log_structured_output_audit(
    *,
    model_name: str,
    structured_output: ModelStructuredOutputRequest,
    response_id: str | None,
    provider_status: str,
    finish_reason: ModelFinishReason,
    raw_finish_reason: str | None,
    usage: ModelUsage,
    diagnostic: ModelStructuredOutputDiagnostic | None,
) -> None:
    """每次供应商响应只记录安全元数据，成功和失败都不记录输入输出正文。"""

    logger.info(
        "供应商结构化输出审计",
        extra={
            "provider_name": "openai_compatible",
            "model_name": model_name,
            "structured_route": structured_output.route,
            "provider_response_id": response_id,
            "provider_status": provider_status,
            "finish_reason": finish_reason,
            "raw_finish_reason": raw_finish_reason,
            "structured_code": diagnostic.code if diagnostic is not None else None,
            **_structured_schema_audit_fields(structured_output),
            "prompt_tokens": usage.promptTokens,
            "cached_tokens": usage.cachedTokens,
            "completion_tokens": usage.completionTokens,
            "total_tokens": usage.totalTokens,
        },
    )


def _safe_provider_request_id(value: object) -> str | None:
    """只保留短小、可打印的供应商请求 ID，异常头值不进入错误和日志。"""

    if not isinstance(value, str) or not value or len(value) > 256:
        return None
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.:")
    return value if all(character in allowed for character in value) else None


def _provider_transport_error(
    error: APIStatusError | APIConnectionError,
) -> ProviderTransportError:
    """把 SDK 异常压缩成不含响应正文和底层 cause 的稳定错误。"""

    code: ProviderTransportErrorCode
    if isinstance(error, APITimeoutError):
        code = "timeout_error"
        status_code = None
    elif isinstance(error, APIStatusError):
        code = "http_error"
        status_code = error.status_code
    else:
        code = "connection_error"
        status_code = None
    return ProviderTransportError(
        code=code,
        statusCode=status_code,
        requestId=_safe_provider_request_id(getattr(error, "request_id", None)),
    )


def _log_structured_transport_failure(
    *,
    model_name: str,
    structured_output: ModelStructuredOutputRequest,
    error: ProviderTransportError,
) -> None:
    """传输失败只记录安全异常字段，禁止读取或输出 SDK 错误正文。"""

    provider_status = f"http_{error.statusCode}" if error.statusCode is not None else error.code
    logger.warning(
        "供应商结构化输出传输失败",
        extra={
            "provider_name": "openai_compatible",
            "model_name": model_name,
            "structured_route": structured_output.route,
            "provider_response_id": error.requestId,
            "provider_status": provider_status,
            "finish_reason": "unknown",
            "raw_finish_reason": provider_status,
            "structured_code": error.code,
            **_structured_schema_audit_fields(structured_output),
            "prompt_tokens": 0,
            "cached_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        },
    )


def _capture_structured_transport_error(
    *,
    model_name: str,
    structured_output: ModelStructuredOutputRequest,
    error: APIStatusError | APIConnectionError,
) -> ProviderTransportError:
    """在捕获块内只提取安全字段；调用方必须离开捕获块后再抛出。"""

    safe_error = _provider_transport_error(error)
    _log_structured_transport_failure(
        model_name=model_name,
        structured_output=structured_output,
        error=safe_error,
    )
    return safe_error


def _structured_turn_result(
    *,
    model_name: str,
    request: ModelTurnRequest,
    structured_output: dict[str, Any] | None,
    diagnostic: ModelStructuredOutputDiagnostic | None,
    usage: ModelUsage,
    finish_reason: ModelFinishReason,
    raw_finish_reason: str | None,
    recovery_code: StructuredOutputRecoveryCode | None = None,
) -> ModelTurnResult:
    """统一构造无可见正文、无工具调用的结构化结果。"""

    structured_request = request.structuredOutput
    if structured_request is None:
        raise ValueError("结构化结果缺少 structuredOutput 请求")
    if recovery_code is not None:
        _log_structured_output_recovery(
            model_name=model_name,
            structured_output=structured_request,
            recovery_code=recovery_code,
            usage=usage,
        )
    if diagnostic is not None:
        _log_structured_output_diagnostic(
            model_name=model_name,
            structured_output=structured_request,
            diagnostic=diagnostic,
            usage=usage,
        )
    return ModelTurnResult(
        content="",
        toolCalls=[],
        structuredOutput=structured_output,
        structuredOutputDiagnostic=diagnostic,
        structuredOutputCorrectionCount=1 if recovery_code is not None else 0,
        usage=usage,
        finishReason=finish_reason,
        rawFinishReason=raw_finish_reason,
        effectiveMaxOutputTokens=request.maxOutputTokens,
    )


def _append_missing_container_closers(value: str) -> tuple[str, int] | None:
    """只追加缺失的对象/数组闭合符；不修字符串、标点、键或值。"""

    stack: list[str] = []
    in_string = False
    escaped = False
    unicode_digits_remaining = 0
    for character in value:
        if in_string:
            if unicode_digits_remaining:
                if character not in "0123456789abcdefABCDEF":
                    return None
                unicode_digits_remaining -= 1
                continue
            if escaped:
                if character == "u":
                    unicode_digits_remaining = 4
                elif character not in '"\\/bfnrt':
                    return None
                escaped = False
                continue
            if character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            elif ord(character) < 0x20:
                return None
            continue

        if character == '"':
            in_string = True
        elif character in "{[":
            stack.append(character)
            if len(stack) > _MAX_RECOVERY_CONTAINER_DEPTH:
                return None
        elif character in "}]":
            if not stack:
                return None
            opener = stack.pop()
            if (opener, character) not in {("{", "}"), ("[", "]")}:
                return None

    if in_string or escaped or unicode_digits_remaining or not stack:
        return None
    suffix = "".join("}" if opener == "{" else "]" for opener in reversed(stack))
    return value + suffix, len(stack)


def _recover_single_strict_tool_call(
    *,
    response: AIMessage,
    request: ModelTurnRequest,
    finish_reason: ModelFinishReason,
) -> tuple[ModelToolCall, int] | None:
    """在唯一 strict 工具响应中尝试一次追加容器闭合符恢复。"""

    if (
        finish_reason != "tool_calls"
        or not isinstance(response.content, str)
        or response.content.strip()
        or request.requiredToolName is None
        or request.parallelToolCalls
        or len(request.tools) != 1
        or not request.tools[0].strict
        or response.tool_calls
        or len(response.invalid_tool_calls) != 1
    ):
        return None
    invalid_call = response.invalid_tool_calls[0]
    if (
        invalid_call.get("name") != request.requiredToolName
        or _invalid_tool_call_code(invalid_call) != "json_decode_error"
    ):
        return None
    raw_arguments = invalid_call.get("args")
    if not isinstance(raw_arguments, str):
        return None
    repaired = _append_missing_container_closers(raw_arguments)
    if repaired is None:
        return None
    candidate, appended_count = repaired
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    try:
        # 恢复后仍以原工具完整 schema 为准；未知字段和缺失字段不会被放行。
        jsonschema_rs.validate(request.tools[0].parameters, parsed)
    except ValueError:
        return None
    return (
        ModelToolCall(
            id=str(invalid_call.get("id", "")),
            name=request.requiredToolName,
            arguments=parsed,
        ),
        appended_count,
    )


class OpenAICompatibleProvider:
    supports_request_idempotency = False
    billable = True
    provider_name = "openai_compatible"
    transport_profile = "transport.openai-compatible.v1"
    capability_version = "capability.openai-compatible.structured-output.v1"

    def __init__(self, settings: Settings) -> None:
        if settings.openai_api_key is None or not settings.openai_api_key.get_secret_value():
            raise ValueError("真实模型提供方缺少 OPENAI_API_KEY")
        api_key = settings.openai_api_key.get_secret_value()
        self._model = ChatOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            model=settings.openai_model,
            temperature=0,
        )
        strict_base_url = _resolve_deepseek_strict_base_url(settings)
        self._strict_model = (
            ChatOpenAI(
                api_key=settings.openai_api_key,
                base_url=strict_base_url,
                model=settings.openai_model,
                temperature=0,
                # strict 阶段的纠正次数由视频规划器统一治理，禁止 SDK 暗中重发。
                max_retries=0,
            )
            if _is_deepseek_model(settings.openai_model) and strict_base_url is not None
            else None
        )
        # 结构化文本通道直接使用官方 SDK，禁用 SDK 隐式重试，由上层统一治理调用预算。
        self._structured_chat_client = AsyncOpenAI(
            api_key=api_key,
            base_url=settings.openai_base_url,
            max_retries=0,
        )
        self._responses_client = (
            AsyncOpenAI(
                api_key=api_key,
                # DeepSeek Responses 是标准根地址能力，不能复用 strict 的 /beta。
                base_url=_DEEPSEEK_STANDARD_BASE_URL,
                max_retries=0,
            )
            if (
                _is_official_deepseek_endpoint(settings.openai_base_url)
                and settings.openai_model.strip().casefold() == _DEEPSEEK_RESPONSES_MODEL
            )
            else None
        )
        self.model_name = settings.openai_model
        self.endpoint_profile = (
            "endpoint.deepseek-official.v1"
            if _is_official_deepseek_endpoint(settings.openai_base_url)
            else "endpoint.openai-compatible-custom.v1"
        )

    def supports_structured_output(self, route: ModelStructuredOutputRoute) -> bool:
        """报告当前实例可实际调用的结构化输出路由。"""

        if route == "responses_json_schema_v1":
            return self._responses_client is not None
        return route == "chat_json_output_v1"

    async def _complete_responses_json_schema(
        self,
        *,
        request: ModelTurnRequest,
        structured_output: ModelStructuredOutputRequest,
        validator: jsonschema_rs.Validator,
    ) -> ModelTurnResult:
        """调用 DeepSeek 官方 Responses JSON Schema，且只接受唯一文本对象。"""

        if self._responses_client is None:
            raise ValueError("responses_json_schema_v1 仅支持 DeepSeek 官方 deepseek-v4-flash")
        wire_schema = _compile_responses_wire_schema(structured_output)
        call_options: dict[str, Any] = {
            "model": self.model_name,
            "input": _responses_input_payloads(request),
            "max_output_tokens": request.maxOutputTokens,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": structured_output.name,
                    # Responses 只接收供应商兼容子集；完整原 Schema 仍由本地 validator 裁决。
                    "schema": wire_schema,
                }
            },
        }
        if request.thinkingMode == "disabled":
            # Responses 使用 effort=none 关闭思考，避免推理 token 挤占可见结构预算。
            call_options["reasoning"] = {"effort": "none"}
        response: Any | None = None
        transport_error: ProviderTransportError | None = None
        try:
            response = await self._responses_client.responses.create(**call_options)
        except APITimeoutError as exc:
            transport_error = _capture_structured_transport_error(
                model_name=self.model_name,
                structured_output=structured_output,
                error=exc,
            )
        except (APIStatusError, APIConnectionError) as exc:
            transport_error = _capture_structured_transport_error(
                model_name=self.model_name,
                structured_output=structured_output,
                error=exc,
            )
        # 必须离开 except 后再抛出，确保原始 SDK 异常不会挂到 __context__。
        if transport_error is not None:
            raise transport_error
        if response is None:
            raise RuntimeError("供应商 Responses SDK 未返回响应")
        payload = cast(dict[str, Any], response.model_dump(mode="python"))
        usage = _usage_from_payload(payload, responses=True)
        status = payload.get("status")
        details = payload.get("incomplete_details")
        raw_incomplete_reason = details.get("reason") if isinstance(details, Mapping) else None
        audit_finish_reason: ModelFinishReason = (
            "stop"
            if status == "completed"
            else "length"
            if status == "incomplete" and raw_incomplete_reason == "max_output_tokens"
            else "content_filter"
            if status == "incomplete" and raw_incomplete_reason == "content_filter"
            else "unknown"
        )
        response_id = payload.get("id")
        _log_structured_output_audit(
            model_name=self.model_name,
            structured_output=structured_output,
            response_id=response_id if isinstance(response_id, str) else None,
            provider_status=status if isinstance(status, str) else "unknown",
            finish_reason=audit_finish_reason,
            raw_finish_reason=(
                f"response.incomplete:{raw_incomplete_reason}"
                if raw_incomplete_reason in {"max_output_tokens", "content_filter"}
                else f"response.{status}"
                if status in {"completed", "failed", "incomplete"}
                else "response.unknown_status"
            ),
            usage=usage,
            diagnostic=None,
        )
        if status == "incomplete":
            raw_reason = details.get("reason") if isinstance(details, Mapping) else None
            finish_reason: ModelFinishReason = (
                "length"
                if raw_reason == "max_output_tokens"
                else "content_filter"
                if raw_reason == "content_filter"
                else "unknown"
            )
            return _structured_turn_result(
                model_name=self.model_name,
                request=request,
                structured_output=None,
                diagnostic=ModelStructuredOutputDiagnostic(
                    code="response_incomplete",
                    jsonPointer="",
                    keyword="status",
                ),
                usage=usage,
                finish_reason=finish_reason,
                raw_finish_reason=(
                    f"response.incomplete:{raw_reason}"
                    if raw_reason in {"max_output_tokens", "content_filter"}
                    else "response.incomplete"
                ),
            )
        if status == "failed":
            return _structured_turn_result(
                model_name=self.model_name,
                request=request,
                structured_output=None,
                diagnostic=ModelStructuredOutputDiagnostic(
                    code="response_failed",
                    jsonPointer="",
                    keyword="status",
                ),
                usage=usage,
                finish_reason="unknown",
                raw_finish_reason="response.failed",
            )
        if status != "completed":
            return _structured_turn_result(
                model_name=self.model_name,
                request=request,
                structured_output=None,
                diagnostic=ModelStructuredOutputDiagnostic(
                    code="unexpected_output",
                    jsonPointer="",
                    keyword="status",
                ),
                usage=usage,
                finish_reason="unknown",
                raw_finish_reason="response.unknown_status",
            )

        raw_output = payload.get("output")
        output_items = raw_output if isinstance(raw_output, list) else []
        text_blocks: list[str] = []
        unexpected_output = not isinstance(raw_output, list)
        has_incomplete_item = False
        for item in output_items:
            if not isinstance(item, Mapping):
                unexpected_output = True
                continue
            item_type = item.get("type")
            if item_type == "reasoning":
                continue
            if item_type != "message":
                unexpected_output = True
                continue
            if item.get("status") in {"in_progress", "incomplete"}:
                has_incomplete_item = True
            raw_content = item.get("content")
            if not isinstance(raw_content, list):
                unexpected_output = True
                continue
            for content_item in raw_content:
                if (
                    not isinstance(content_item, Mapping)
                    or content_item.get("type") != "output_text"
                    or not isinstance(content_item.get("text"), str)
                ):
                    unexpected_output = True
                    continue
                text_blocks.append(cast(str, content_item["text"]))
        if has_incomplete_item:
            return _structured_turn_result(
                model_name=self.model_name,
                request=request,
                structured_output=None,
                diagnostic=ModelStructuredOutputDiagnostic(
                    code="response_incomplete",
                    jsonPointer="",
                    keyword="status",
                ),
                usage=usage,
                finish_reason="unknown",
                raw_finish_reason="response.completed:item_incomplete",
            )
        if unexpected_output:
            return _structured_turn_result(
                model_name=self.model_name,
                request=request,
                structured_output=None,
                diagnostic=ModelStructuredOutputDiagnostic(
                    code="unexpected_output",
                    jsonPointer="",
                    keyword="output",
                ),
                usage=usage,
                finish_reason="unknown",
                raw_finish_reason="response.completed",
            )
        if len(text_blocks) > 1:
            return _structured_turn_result(
                model_name=self.model_name,
                request=request,
                structured_output=None,
                diagnostic=ModelStructuredOutputDiagnostic(
                    code="multiple_text_outputs",
                    jsonPointer="",
                    keyword="content",
                ),
                usage=usage,
                finish_reason="stop",
                raw_finish_reason="response.completed",
            )
        raw_text = text_blocks[0] if text_blocks else ""
        parsed, diagnostic, recovery_code = _parse_and_validate_structured_output(
            raw_text=raw_text,
            structured_output=structured_output,
            validator=validator,
        )
        return _structured_turn_result(
            model_name=self.model_name,
            request=request,
            structured_output=parsed,
            diagnostic=diagnostic,
            usage=usage,
            finish_reason="stop",
            raw_finish_reason="response.completed",
            recovery_code=recovery_code,
        )

    async def _complete_chat_json_output(
        self,
        *,
        request: ModelTurnRequest,
        structured_output: ModelStructuredOutputRequest,
        validator: jsonschema_rs.Validator,
    ) -> ModelTurnResult:
        """调用普通 Chat JSON Output；只保证 JSON 语法，Schema 仍由本地复验。"""

        if not any("json" in message.content.casefold() for message in request.messages):
            # DeepSeek 官方要求提示正文显式包含 json；缺失时可能持续输出空白直至耗尽额度。
            raise ValueError("chat_json_output_v1 的消息正文必须显式包含 json")
        call_options: dict[str, Any] = {
            "model": self.model_name,
            "messages": _chat_message_payloads(request),
            "max_tokens": request.maxOutputTokens,
            "response_format": {"type": "json_object"},
        }
        if request.thinkingMode == "disabled":
            call_options["extra_body"] = {"thinking": {"type": "disabled"}}
        response: Any | None = None
        transport_error: ProviderTransportError | None = None
        try:
            response = await self._structured_chat_client.chat.completions.create(**call_options)
        except APITimeoutError as exc:
            transport_error = _capture_structured_transport_error(
                model_name=self.model_name,
                structured_output=structured_output,
                error=exc,
            )
        except (APIStatusError, APIConnectionError) as exc:
            transport_error = _capture_structured_transport_error(
                model_name=self.model_name,
                structured_output=structured_output,
                error=exc,
            )
        # Chat 路由同样要在捕获块外抛出，不能只依赖 `from None` 隐藏上下文。
        if transport_error is not None:
            raise transport_error
        if response is None:
            raise RuntimeError("供应商 Chat SDK 未返回响应")
        payload = cast(dict[str, Any], response.model_dump(mode="python"))
        usage = _usage_from_payload(payload, responses=False)
        raw_choices = payload.get("choices")
        choices = raw_choices if isinstance(raw_choices, list) else []
        audit_choice = choices[0] if len(choices) == 1 else None
        audit_raw_finish_reason = (
            audit_choice.get("finish_reason") if isinstance(audit_choice, Mapping) else None
        )
        audit_finish_reason = normalize_finish_reason(audit_raw_finish_reason)
        response_id = payload.get("id")
        _log_structured_output_audit(
            model_name=self.model_name,
            structured_output=structured_output,
            response_id=response_id if isinstance(response_id, str) else None,
            provider_status="chat_completion",
            finish_reason=audit_finish_reason,
            raw_finish_reason=_raw_finish_reason(audit_raw_finish_reason),
            usage=usage,
            diagnostic=None,
        )
        if len(choices) > 1:
            return _structured_turn_result(
                model_name=self.model_name,
                request=request,
                structured_output=None,
                diagnostic=ModelStructuredOutputDiagnostic(
                    code="multiple_text_outputs",
                    jsonPointer="",
                    keyword="choices",
                ),
                usage=usage,
                finish_reason="unknown",
                raw_finish_reason=None,
            )
        if not choices or not isinstance(choices[0], Mapping):
            return _structured_turn_result(
                model_name=self.model_name,
                request=request,
                structured_output=None,
                diagnostic=ModelStructuredOutputDiagnostic(
                    code="empty_output",
                    jsonPointer="",
                    keyword="content",
                ),
                usage=usage,
                finish_reason="unknown",
                raw_finish_reason=None,
            )
        choice = choices[0]
        provider_finish_reason = choice.get("finish_reason")
        finish_reason = normalize_finish_reason(provider_finish_reason)
        raw_finish_reason = _raw_finish_reason(provider_finish_reason)
        if finish_reason == "length":
            return _structured_turn_result(
                model_name=self.model_name,
                request=request,
                structured_output=None,
                diagnostic=ModelStructuredOutputDiagnostic(
                    code="response_incomplete",
                    jsonPointer="",
                    keyword="finishReason",
                ),
                usage=usage,
                finish_reason=finish_reason,
                raw_finish_reason=raw_finish_reason,
            )
        if finish_reason == "content_filter":
            return _structured_turn_result(
                model_name=self.model_name,
                request=request,
                structured_output=None,
                diagnostic=ModelStructuredOutputDiagnostic(
                    code="response_failed",
                    jsonPointer="",
                    keyword="finishReason",
                ),
                usage=usage,
                finish_reason=finish_reason,
                raw_finish_reason=raw_finish_reason,
            )
        if finish_reason != "stop":
            return _structured_turn_result(
                model_name=self.model_name,
                request=request,
                structured_output=None,
                diagnostic=ModelStructuredOutputDiagnostic(
                    code="unexpected_output",
                    jsonPointer="",
                    keyword="finishReason",
                ),
                usage=usage,
                finish_reason=finish_reason,
                raw_finish_reason=raw_finish_reason,
            )
        raw_message = choice.get("message")
        message = raw_message if isinstance(raw_message, Mapping) else {}
        if message.get("tool_calls"):
            return _structured_turn_result(
                model_name=self.model_name,
                request=request,
                structured_output=None,
                diagnostic=ModelStructuredOutputDiagnostic(
                    code="unexpected_output",
                    jsonPointer="",
                    keyword="toolCalls",
                ),
                usage=usage,
                finish_reason=finish_reason,
                raw_finish_reason=raw_finish_reason,
            )
        raw_content = message.get("content")
        if raw_content is not None and not isinstance(raw_content, str):
            return _structured_turn_result(
                model_name=self.model_name,
                request=request,
                structured_output=None,
                diagnostic=ModelStructuredOutputDiagnostic(
                    code="unexpected_output",
                    jsonPointer="",
                    keyword="content",
                ),
                usage=usage,
                finish_reason=finish_reason,
                raw_finish_reason=raw_finish_reason,
            )
        parsed, diagnostic, recovery_code = _parse_and_validate_structured_output(
            raw_text=raw_content or "",
            structured_output=structured_output,
            validator=validator,
        )
        return _structured_turn_result(
            model_name=self.model_name,
            request=request,
            structured_output=parsed,
            diagnostic=diagnostic,
            usage=usage,
            finish_reason=finish_reason,
            raw_finish_reason=raw_finish_reason,
            recovery_code=recovery_code,
        )

    async def complete_turn(self, request: ModelTurnRequest) -> ModelTurnResult:
        if request.structuredOutput is not None:
            validator = _compile_structured_output_schema(request.structuredOutput)
            if request.structuredOutput.route == "responses_json_schema_v1":
                return await self._complete_responses_json_schema(
                    request=request,
                    structured_output=request.structuredOutput,
                    validator=validator,
                )
            return await self._complete_chat_json_output(
                request=request,
                structured_output=request.structuredOutput,
                validator=validator,
            )
        is_deepseek = _is_deepseek_model(self.model_name)
        strict_tool_count = sum(tool.strict for tool in request.tools)
        if is_deepseek and 0 < strict_tool_count < len(request.tools):
            # DeepSeek strict Beta 要求同一请求中的全部函数都开启 strict；混用时必须在
            # bind_tools/ainvoke 之前失败，不能静默升级工具或退回普通通道。
            raise ValueError("DeepSeek 工具请求不能混用 strict 与非 strict 函数")
        use_deepseek_strict_channel = is_deepseek and strict_tool_count > 0
        if use_deepseek_strict_channel:
            if self._strict_model is None:
                raise ValueError("DeepSeek strict 工具请求缺少 OPENAI_STRICT_BASE_URL")
            model: Any = self._strict_model
        else:
            model = self._model
        if request.tools:
            # DeepSeek 与 OpenAI 兼容接口都通过函数声明中的 strict 开启结构约束。
            bind_options: dict[str, object] = {}
            if request.requiredToolName is not None:
                # named tool_choice 比 required 更窄，确保供应商只能选择指定函数。
                bind_options["tool_choice"] = request.requiredToolName
            if not request.parallelToolCalls and not (
                use_deepseek_strict_channel
                and request.requiredToolName is not None
                and len(request.tools) == 1
            ):
                # DeepSeek strict 的 named 单工具请求不下发官方文档未列出的字段；
                # parallelToolCalls=false 仍由本地恢复和唯一调用门禁直接读取。
                bind_options["parallel_tool_calls"] = False
            model = model.bind_tools(
                [
                    {
                        "type": "function",
                        "function": {
                            "name": tool.name,
                            "description": tool.description,
                            "parameters": tool.parameters,
                            "strict": tool.strict,
                        },
                    }
                    for tool in request.tools
                ],
                **bind_options,
            )
        messages: list[BaseMessage] = []
        for message in request.messages:
            if message.role == "system":
                messages.append(SystemMessage(content=message.content, name=message.name))
            elif message.role == "user":
                messages.append(HumanMessage(content=message.content, name=message.name))
            elif message.role == "assistant":
                messages.append(
                    AIMessage(
                        content=message.content,
                        tool_calls=[
                            {
                                "id": tool_call.id,
                                "name": tool_call.name,
                                "args": tool_call.arguments,
                                "type": "tool_call",
                            }
                            for tool_call in message.tool_calls
                        ],
                    )
                )
            elif message.tool_call_id is not None:
                messages.append(
                    ToolMessage(
                        content=message.content,
                        tool_call_id=message.tool_call_id,
                        name=message.name,
                    )
                )
            else:
                raise ValueError("工具消息缺少 toolCallId")
        invocation_options: dict[str, object] = {}
        if is_deepseek:
            # ChatOpenAI 会把普通 max_tokens 改名，DeepSeek 必须通过 extra_body 保留原字段。
            deepseek_body: dict[str, object] = {"max_tokens": request.maxOutputTokens}
            if request.thinkingMode == "disabled":
                # V4 默认开启思考；strict 工具任务关闭思考，避免推理 token 挤占预授权输出。
                deepseek_body["thinking"] = {"type": "disabled"}
            invocation_options["extra_body"] = deepseek_body
        else:
            invocation_options["max_tokens"] = request.maxOutputTokens
            if request.thinkingMode == "disabled":
                invocation_options["extra_body"] = {"thinking": {"type": "disabled"}}
        response: AIMessage | None = None
        transport_error: ProviderTransportError | None = None
        try:
            response = cast(
                AIMessage,
                await model.ainvoke(messages, **invocation_options),
            )
        except APITimeoutError as exc:
            transport_error = _provider_transport_error(exc)
        except (APIStatusError, APIConnectionError) as exc:
            transport_error = _provider_transport_error(exc)
        # 普通工具通道同样在捕获块外抛出，避免 SDK 响应正文留在异常上下文中。
        if transport_error is not None:
            raise transport_error
        if response is None:
            raise RuntimeError("供应商 Chat SDK 未返回响应")
        if not isinstance(response.content, str):
            raise ValueError("模型返回了不支持的非文本可见内容")

        usage: Mapping[str, Any] = response.usage_metadata or {}
        input_details = usage.get("input_token_details") or {}
        prompt_tokens = int(usage.get("input_tokens", 0))
        completion_tokens = int(usage.get("output_tokens", 0))
        total_tokens = int(usage.get("total_tokens", prompt_tokens + completion_tokens))
        cached_tokens = int(input_details.get("cache_read", 0))
        provider_finish_reason = response.response_metadata.get("finish_reason")
        finish_reason = normalize_finish_reason(provider_finish_reason)
        request_tools_by_name = {tool.name: tool for tool in request.tools}
        tool_calls: list[ModelToolCall] = []
        strict_schema_violation_names: list[str] = []
        for parsed_tool_call in response.tool_calls:
            tool_name = str(parsed_tool_call["name"])
            arguments = parsed_tool_call.get("args", {})
            requested_tool = request_tools_by_name.get(tool_name)
            if requested_tool is not None and requested_tool.strict:
                try:
                    # LangChain 解析成功只证明 JSON 可读；进入业务层前仍以本轮原 Schema 为准。
                    jsonschema_rs.validate(requested_tool.parameters, arguments)
                except ValueError:
                    schema_sha256 = _schema_sha256(requested_tool.parameters)
                    strict_schema_violation_names.append(tool_name)
                    logger.warning(
                        "供应商 strict 工具参数未通过本地 Schema 复验",
                        extra={
                            "model_name": self.model_name,
                            "tool_name": tool_name,
                            "schema_sha256": schema_sha256,
                            "finish_reason": finish_reason,
                            "prompt_tokens": prompt_tokens,
                            "cached_tokens": cached_tokens,
                            "completion_tokens": completion_tokens,
                            "total_tokens": total_tokens,
                        },
                    )
                    continue
            tool_calls.append(
                ModelToolCall(
                    id=str(parsed_tool_call.get("id", "")),
                    name=tool_name,
                    arguments=arguments,
                )
            )
        recovery = _recover_single_strict_tool_call(
            response=response,
            request=request,
            finish_reason=finish_reason,
        )
        recovered_codes: list[ModelToolRecoveryCode] = []
        recovered_container_counts: list[int] = []
        invalid_tool_calls = response.invalid_tool_calls
        if recovery is not None:
            recovered_call, appended_count = recovery
            tool_calls.append(recovered_call)
            recovered_codes.append("append_container_closers")
            recovered_container_counts.append(appended_count)
            invalid_tool_calls = []
        allowed_tool_names = {tool.name for tool in request.tools}
        invalid_tool_call_names: list[str] = []
        for invalid_tool_call in invalid_tool_calls:
            raw_name = invalid_tool_call.get("name")
            invalid_tool_call_names.append(
                raw_name
                if isinstance(raw_name, str) and raw_name in allowed_tool_names
                else "未知工具"
            )
        invalid_tool_call_codes = [
            _invalid_tool_call_code(tool_call) for tool_call in invalid_tool_calls
        ]
        invalid_tool_call_argument_character_counts = [
            _argument_character_count(tool_call) for tool_call in invalid_tool_calls
        ]
        for tool_name in strict_schema_violation_names:
            invalid_tool_call_names.append(tool_name)
            invalid_tool_call_codes.append("provider_strict_schema_violation")
            # LangChain 已丢失原始 JSON 字符串；不为诊断重新序列化参数正文。
            invalid_tool_call_argument_character_counts.append(0)
        return ModelTurnResult(
            content=response.content,
            toolCalls=tool_calls,
            invalidToolCallCount=(len(invalid_tool_calls) + len(strict_schema_violation_names)),
            invalidToolCallNames=invalid_tool_call_names,
            invalidToolCallCodes=invalid_tool_call_codes,
            invalidToolCallArgumentCharacterCounts=(invalid_tool_call_argument_character_counts),
            recoveredToolCallCount=len(recovered_codes),
            recoveredToolCallCodes=recovered_codes,
            recoveredToolCallAppendedContainerCounts=recovered_container_counts,
            finishReason=finish_reason,
            rawFinishReason=_raw_finish_reason(provider_finish_reason),
            effectiveMaxOutputTokens=request.maxOutputTokens,
            usage=ModelUsage(
                promptTokens=prompt_tokens,
                cachedTokens=cached_tokens,
                completionTokens=completion_tokens,
                totalTokens=total_tokens,
            ),
            providerResponseId=_raw_finish_reason(response.response_metadata.get("id")),
            reasoningContent=(
                response.additional_kwargs.get("reasoning_content")
                if isinstance(response.additional_kwargs.get("reasoning_content"), str)
                else None
            ),
        )
